import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from re import Pattern
from types import TracebackType
from typing import Any, Callable, Generic, TypeVar, cast

from ididi import Graph, Resolver
from ididi.interfaces import IDependent
from msgspec import Struct, ValidationError
from msgspec.json import Decoder
from msgspec.structs import asdict as struct_asdict

from lihil.asgi import ASGIRoute
from lihil.errors import SockRejectedError
from lihil.interface import (
    ASGIApp,
    Base,
    IAsyncFunc,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    Record,
)
from lihil.vendors import WebSocket, WebSocketDisconnect, WebSocketState

from .bus import InMemorySocketBus, SocketBus
from .channel import ChannelBase
from .dispatcher import ChannelDispatcher
from .protocol import (
    EVENT_NOT_FOUND,
    TOPIC_NOT_FOUND,
    MessageEnvelope,
    error_payload,
    is_reply_payload,
    reply_payload,
)


def Topic(pattern: str) -> re.Pattern[str]:
    """
    Factory: compile topic pattern into a regex with named groups.
    """
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i] == "{":
            end = pattern.find("}", i)
            if end == -1:
                raise ValueError(f"Invalid topic pattern: {pattern}")
            name = pattern[i + 1 : end]
            parts.append(rf"(?P<{name}>[^/]+)")
            i = end + 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


class ISocket:
    """
    Composition wrapper around starlette's WebSocket.
    Exposes a curated API surface plus channel helpers.
    """

    _msg_decoder = Decoder(type=MessageEnvelope)

    def __init__(self, websocket: WebSocket):
        self._ws = websocket
        self._seq = 0

    @property
    def websocket(self) -> WebSocket:
        return self._ws

    @property
    def application_state(self) -> WebSocketState:
        return self._ws.application_state

    @property
    def client_state(self) -> WebSocketState:
        return self._ws.client_state

    @property
    def dual_connected(self) -> bool:
        return (
            self._ws.client_state == WebSocketState.CONNECTED
            and self._ws.application_state == WebSocketState.CONNECTED
        )

    @property
    def scope(self) -> Any:
        return self._ws.scope

    @property
    def state(self) -> Any:
        return self._ws.state

    @property
    def headers(self) -> Any:
        return self._ws.headers

    @property
    def query_params(self) -> Any:
        return self._ws.query_params

    @property
    def path_params(self) -> Any:
        return self._ws.path_params

    @property
    def url(self) -> Any:
        return self._ws.url

    async def accept(self, subprotocol: str | None = None) -> None:
        await self._ws.accept(subprotocol=subprotocol)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        await self._ws.close(code=code, reason=reason or "")

    async def send_json(self, data: Any) -> None:
        await self._ws.send_json(data)

    async def send_text(self, data: str) -> None:
        await self._ws.send_text(data)

    async def send_bytes(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def receive_json(self) -> Any:
        return await self._ws.receive_json()

    async def receive_text(self) -> str:
        return await self._ws.receive_text()

    async def receive_bytes(self) -> bytes:
        return await self._ws.receive_bytes()

    async def receive_message(self) -> MessageEnvelope:
        content = await self._ws.receive_bytes()
        return self._msg_decoder.decode(content)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _to_jsonable(self, data: Any) -> Any:
        if isinstance(data, Base):
            return self._to_jsonable(data.asdict())
        if isinstance(data, Struct):
            return self._to_jsonable(struct_asdict(data))
        if isinstance(data, dict):
            return {key: self._to_jsonable(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self._to_jsonable(value) for value in data]
        if isinstance(data, tuple):
            return [self._to_jsonable(value) for value in data]
        return data

    async def send_envelope(
        self,
        topic: str,
        event: str,
        payload: Any = None,
        *,
        ref: str | None = None,
        join_ref: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._ws.send_json(
            {
                "topic": topic,
                "event": event,
                "payload": self._to_jsonable(payload),
                "ref": ref,
                "join_ref": join_ref,
                "event_id": event_id,
                "seq": self._next_seq(),
            }
        )

    async def reply(
        self,
        topic: str,
        payload: Any,
        event: str = "reply",
        *,
        ref: str | None = None,
        join_ref: str | None = None,
    ) -> None:
        await self.send_envelope(
            topic, event, payload, ref=ref, join_ref=join_ref
        )

    async def send_reply(
        self,
        topic: str,
        response: Any | None = None,
        *,
        ref: str | None = None,
        join_ref: str | None = None,
    ) -> None:
        await self.reply(
            topic,
            reply_payload(response),
            ref=ref,
            join_ref=join_ref,
        )

    async def send_error(
        self,
        topic: str,
        code: str,
        *,
        message: str | None = None,
        detail: Any | None = None,
        ref: str | None = None,
        join_ref: str | None = None,
    ) -> None:
        await self.reply(
            topic,
            error_payload(code, message=message, detail=detail),
            ref=ref,
            join_ref=join_ref,
        )

    async def emit(self, topic: str, payload: Any, event: str = "emit") -> None:
        await self.send_envelope(topic, event, payload)

    async def allow_if(
        self, condition: bool, code: int = 4403, reason: str = "Forbidden"
    ):
        if not condition:
            await self._ws.close(code=code, reason=reason)
            raise SockRejectedError("connection rejected")


CFactory = TypeVar("CFactory", bound=ChannelBase)


class ChannelFactory(Record, Generic[CFactory]):
    topic_pattern: Pattern[str]
    channel_type: type[CFactory]

    def extra_topic_params(self, raw_topic: str) -> dict[str, Any] | None:
        if not (res := self.topic_pattern.match(raw_topic)):
            return None

        return res.groupdict()


class SocketSession:
    "Encapsulation for socket connection and related dependnecies"

    def __init__(
        self,
        socket: ISocket,
        bus: SocketBus,
        resolver: Resolver,
        channel_fractories: list[ChannelFactory[ChannelBase]],
        connect_cb: IAsyncFunc[..., None] | None,
        disconnect_cb: IAsyncFunc[..., None] | None,
    ):
        self._socket = socket
        self._bus = bus
        self._resolver = resolver
        self._channel_factories = channel_fractories

        self._connect_cb = connect_cb
        self._disconnect_cb = disconnect_cb
        self._subscriptions: dict[str, ChannelBase] = {}
        self._dispatcher = ChannelDispatcher()

    async def __aenter__(self):
        if self._connect_cb:
            await self._connect_cb(self._socket)

        await self._socket.accept()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        unexpected_error = exc_type not in (
            WebSocketDisconnect,
            SockRejectedError,
            None,
        )
        if unexpected_error and self._socket.dual_connected:
            await self._socket.close(code=1011, reason="Internal Server Error")

        for channel in list(self._subscriptions.values()):
            await channel.aclose()
        self._subscriptions.clear()

        if self._disconnect_cb:
            await self._disconnect_cb(self._socket)

        if not unexpected_error and self._socket.dual_connected:
            await self._socket.close()
        return not unexpected_error and exc_type in (
            WebSocketDisconnect,
            SockRejectedError,
        )

    async def message_loop(self):
        while True:
            msg_env = await self._socket.receive_message()
            async with self._resolver.ascope() as asc:
                await self.handle_message(msg_env, asc)

    async def create_channel(
        self,
        topic: str,
        channel_factory: ChannelFactory[ChannelBase],
        resolver: Resolver,
    ) -> ChannelBase:
        channel = await resolver.aresolve(
            channel_factory.channel_type,
            topic=topic,
            socket=self._socket,
            bus=self._bus,
            resolver=resolver,
        )
        return channel

    def _topic_exists(self, topic: str) -> bool:
        return any(
            factory.extra_topic_params(topic) is not None
            for factory in self._channel_factories
        )

    async def _send_not_joined_or_missing(self, msg: MessageEnvelope) -> None:
        if self._topic_exists(msg.topic):
            await self._socket.send_error(
                msg.topic, "not_joined", ref=msg.ref, join_ref=msg.join_ref
            )
        else:
            await self._socket.send_error(
                msg.topic, "topic_not_found", ref=msg.ref, join_ref=msg.join_ref
            )

    async def _send_join_ack(
        self,
        msg: MessageEnvelope,
        channel: ChannelBase,
        *,
        already_joined: bool = False,
    ) -> None:
        replay_supported = type(channel).replay_after is not ChannelBase.replay_after
        response = {
            "topic": msg.topic,
            "already_joined": already_joined,
            "replay_supported": replay_supported,
        }
        if already_joined:
            join_ref = channel.join_ref or msg.join_ref or msg.ref
        else:
            join_ref = msg.join_ref or msg.ref
        if not already_joined:
            channel.set_join_ref(join_ref)
        await self._socket.send_reply(
            msg.topic, response, ref=msg.ref, join_ref=join_ref
        )

        if not already_joined and replay_supported:
            event_id = None
            if isinstance(msg.payload, dict):
                event_id = msg.payload.get("last_event_id")
            for replayed in await channel.replay_after(event_id):
                await self._socket.send_envelope(
                    replayed.topic,
                    replayed.event,
                    replayed.payload,
                    ref=replayed.ref,
                    join_ref=replayed.join_ref or join_ref,
                    event_id=replayed.event_id,
                )

    async def handle_message(self, msg: MessageEnvelope, resolver: Resolver):
        if msg.topic not in self._subscriptions:
            if msg.event != "join":
                await self._send_not_joined_or_missing(msg)
                return

            for factory in self._channel_factories:
                if (params := factory.extra_topic_params(msg.topic)) is None:
                    continue
                channel = await self.create_channel(msg.topic, factory, resolver)
                self._subscriptions[msg.topic] = channel
                try:
                    await channel.on_join(
                        **self._dispatcher.join_kwargs(channel, params)
                    )
                except SockRejectedError as exc:
                    self._subscriptions.pop(msg.topic, None)
                    await channel.aclose()
                    if self._socket.dual_connected:
                        await self._socket.send_error(
                            msg.topic,
                            "join_rejected",
                            detail={"error": str(exc)},
                            ref=msg.ref,
                            join_ref=msg.join_ref,
                        )
                    return
                except Exception as exc:
                    self._subscriptions.pop(msg.topic, None)
                    await channel.aclose()
                    await self._socket.send_error(
                        msg.topic,
                        "internal_error",
                        detail={"error": str(exc)},
                        ref=msg.ref,
                        join_ref=msg.join_ref,
                    )
                    return
                await self._send_join_ack(msg, channel)
                return
            else:
                await self._socket.send_error(
                    msg.topic, "topic_not_found", ref=msg.ref, join_ref=msg.join_ref
                )
                return
        elif msg.event == "join":
            channel = self._subscriptions[msg.topic]
            await self._send_join_ack(msg, channel, already_joined=True)
        elif msg.event == "exit":
            channel = self._subscriptions.pop(msg.topic)
            await channel.aclose()
            await self._socket.send_reply(
                msg.topic,
                {"topic": msg.topic},
                ref=msg.ref,
                join_ref=msg.join_ref or channel.join_ref,
            )
        else:
            channel = self._subscriptions[msg.topic]
            try:
                reply = await self._dispatcher.dispatch(channel, msg)
            except ValidationError as exc:
                await self._socket.send_error(
                    msg.topic,
                    "invalid_payload",
                    detail={"error": str(exc)},
                    ref=msg.ref,
                    join_ref=msg.join_ref or channel.join_ref,
                )
                return
            except Exception as exc:
                await self._socket.send_error(
                    msg.topic,
                    "internal_error",
                    detail={"error": str(exc)},
                    ref=msg.ref,
                    join_ref=msg.join_ref or channel.join_ref,
                )
                return
            if reply is not None:
                if is_reply_payload(reply):
                    payload = reply
                else:
                    payload = reply_payload(reply)
                await self._socket.reply(
                    msg.topic,
                    payload,
                    ref=msg.ref,
                    join_ref=msg.join_ref or channel.join_ref,
                )


class SocketHub(ASGIRoute):
    call_stack: ASGIApp | None = None

    def __init__(
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        bus_factory: IDependent[SocketBus] = InMemorySocketBus,
    ):
        super().__init__(path, graph=graph, middlewares=middlewares)
        self._on_connect: IAsyncFunc[..., None] | None = None
        self._on_disconnect: IAsyncFunc[..., None] | None = None
        self._bus_factory = bus_factory
        self._channel_factories: list[ChannelFactory[ChannelBase]] = []
        self._dispatcher = ChannelDispatcher()
        self.graph.node(bus_factory)
        self.call_stack: ASGIApp | None = None

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if not self.call_stack:
            raise RuntimeError(f"{self.__class__.__name__}({self._path}) not setup")
        await self.call_stack(scope, receive, send)

    def channel(
        self, channel_cls: Callable[..., ChannelBase]
    ) -> Callable[..., ChannelBase]:
        """
        Register a channel class. Acts as a decorator-friendly helper.
        """
        self.graph.node(
            channel_cls,
            ignore=("socket", "topic", "bus", "resolver"),
        )

        self._dispatcher.validate(cast(type[ChannelBase], channel_cls))
        channel_dep = self.graph.nodes[channel_cls]
        channel_type = cast(type[ChannelBase], channel_dep.dependent)

        factory = ChannelFactory(
            topic_pattern=channel_type.topic,
            channel_type=channel_type,
        )

        self._channel_factories.append(factory)
        self._channel_factories.sort(
            key=lambda cls: len(cls.topic_pattern.groupindex), reverse=True
        )
        return channel_cls

    def on_connect(self, func: IAsyncFunc[..., None]) -> IAsyncFunc[..., None]:
        self._on_connect = func
        return func

    def on_disconnect(self, func: IAsyncFunc[..., None]) -> IAsyncFunc[..., None]:
        self._on_disconnect = func
        return func

    def setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ):
        super().setup(graph=graph, workers=workers)
        self.call_stack = self.chainup_middlewares(self.handle_connection)
        self._is_setup = True

    @asynccontextmanager
    async def create_socket_session(
        self, scope: IScope, receive: IReceive, send: ISend
    ):
        async with self._graph.ascope() as asc:
            socket = ISocket(WebSocket(scope, receive, send))
            bus = await asc.aresolve(SocketBus)
            socket_session = SocketSession(
                socket,
                bus,
                asc,
                self._channel_factories,
                self._on_connect,
                self._on_disconnect,
            )
            exc_type: type[BaseException] | None = None
            exc: BaseException | None = None
            tb: TracebackType | None = None
            entered = False
            try:
                await socket_session.__aenter__()
                entered = True
                yield socket_session
            except WebSocketDisconnect as err:
                exc_type = WebSocketDisconnect
                exc = err
                tb = err.__traceback__
            except SockRejectedError as err:
                exc_type = SockRejectedError
                exc = err
                tb = err.__traceback__
                if not entered:
                    raise
            except BaseException as err:
                exc_type = type(err)
                exc = err
                tb = err.__traceback__
                raise
            finally:
                await socket_session.__aexit__(exc_type, exc, tb)

    async def handle_connection(
        self, scope: IScope, receive: IReceive, send: ISend
    ) -> None:
        if scope["type"] != "websocket":
            raise RuntimeError(
                f"Non-websocket request sent to websocket route {self.path}"
            )

        try:
            async with self.create_socket_session(scope, receive, send) as socket_session:
                await socket_session.message_loop()
        except SockRejectedError:
            return
