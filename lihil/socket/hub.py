import asyncio
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from re import Pattern
from types import TracebackType
from typing import Any, Awaitable, Callable, Generic, TypeVar, cast

from ididi import Graph, Resolver
from ididi.interfaces import IDependent
from msgspec.json import Decoder, encode

from lihil.asgi import ASGIRoute
from lihil.errors import SockRejectedError
from lihil.interface import (
    ASGIApp,
    IAsyncFunc,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    Record,
)
from lihil.vendors import WebSocket, WebSocketDisconnect, WebSocketState

TOPIC_NOT_FOUND = {"code": 4404, "reason": "Topic not found"}
EVENT_NOT_FOUND = {"code": 4404, "reason": "Event not found"}


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


class MessageEnvelope(Record):
    topic: str
    event: str
    payload: Any = None


class ISocket:
    """
    Composition wrapper around starlette's WebSocket.
    Exposes a curated API surface plus channel helpers.
    """

    _msg_decoder = Decoder(type=MessageEnvelope)

    def __init__(self, websocket: WebSocket):
        self._ws = websocket

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

    # Explicitly expose only the supported WebSocket/HTTPConnection API surface
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

    async def reply(self, topic: str, payload: Any, event: str = "reply") -> None:
        await self._ws.send_json({"topic": topic, "event": event, "payload": payload})

    async def emit(self, topic: str, payload: Any, event: str = "emit") -> None:
        await self._ws.send_json({"topic": topic, "event": event, "payload": payload})

    async def allow_if(
        self, condition: bool, code: int = 4403, reason: str = "Forbidden"
    ):
        if not condition:
            await self._ws.close(code=code, reason=reason)
            raise SockRejectedError("connection rejected")


class SocketBus(ABC):  # TODO: rename, this is a general message bus
    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None: ...

    @abstractmethod
    async def unsubscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None: ...

    @abstractmethod
    async def publish(self, topic: str, event: str, payload: Any) -> None:
        """
        Blocking fanout: await delivery to subscribers.
        """

    @abstractmethod
    async def emit(self, topic: str, event: str, payload: Any) -> None:
        """
        Fire-and-forget fanout.
        """


class InMemorySocketBus(SocketBus):
    """
    Simple in-memory bus for topic fanout.
    """

    def __init__(self) -> None:
        self._subs: dict[str, set[Callable[[MessageEnvelope], Awaitable[None]]]] = {}

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None:
        self._subs.setdefault(topic, set()).add(callback)

    async def unsubscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None:
        callbacks = self._subs.get(topic)
        if not callbacks:
            return
        callbacks.discard(callback)
        if not callbacks:
            self._subs.pop(topic, None)

    async def publish(self, topic: str, event: str, payload: Any) -> None:
        envelope = MessageEnvelope(topic=topic, event=event, payload=payload)
        callbacks = list(self._subs.get(topic, set()))
        dead: list[Callable[[MessageEnvelope], Awaitable[None]]] = []
        for cb in callbacks:
            try:
                await cb(envelope)
            except Exception:
                dead.append(cb)
        if dead:
            callbacks_set = self._subs.get(topic)
            if callbacks_set:
                for cb in dead:
                    callbacks_set.discard(cb)
                if not callbacks_set:
                    self._subs.pop(topic, None)

    async def emit(self, topic: str, event: str, payload: Any) -> None:
        asyncio.create_task(self.publish(topic, event, payload))


class ChannelBase(ABC):
    """
    Class-based channel. Subclasses define `topic = Topic("...")` and override hooks.
    """

    topic: re.Pattern[str]

    def __init__(
        self, socket: ISocket, *, topic: str, bus: SocketBus, resolver: Resolver
    ):
        self.socket = socket
        self.bus = bus
        self._resolver = resolver
        self._resolved_topic = topic

    @property
    def resolved_topic(self) -> str:
        return self._resolved_topic

    @classmethod
    def match(cls, topic: str) -> dict[str, str] | None:
        if m := cls.topic.match(topic):
            return m.groupdict()
        return None

    async def publish(self, payload: Any, *, event: str = "broadcast") -> None:
        await self.bus.publish(self._resolved_topic, event=event, payload=payload)

    async def emit(self, payload: Any, *, event: str = "broadcast") -> None:
        # Alias for publish to keep terminology consistent.
        await self.bus.emit(self._resolved_topic, event=event, payload=payload)

    async def on_update(self, env: MessageEnvelope) -> None:
        """
        Default bus subscriber callback: echoes envelope to the socket.
        """
        await self.socket.send_json(
            {"topic": env.topic, "event": env.event, "payload": env.payload}
        )

    async def on_join(self) -> None:
        await self.bus.subscribe(self.resolved_topic, self.on_update)

    @abstractmethod
    async def on_message(self, env: MessageEnvelope) -> Any:
        raise NotImplementedError

    async def on_exit(self) -> None:
        await self.bus.unsubscribe(self.resolved_topic, self.on_update)


CFactory = TypeVar("CFactory", bound=ChannelBase)


class ChannelFactory(Record, Generic[CFactory]):
    topic_pattern: Pattern[str]
    channel_type: type[CFactory]
    channel_factory: Callable[..., CFactory]

    def extract_topic_params(self, raw_topic: str) -> dict[str, Any] | None:
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
        self._channel_stack = AsyncExitStack()

    async def __aenter__(self):
        if self._connect_cb:
            await self._connect_cb(self._socket)

        await self._socket.accept()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | type[None],
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type not in (WebSocketDisconnect, SockRejectedError, None):
            if self._socket.dual_connected:
                await self._socket.close(code=1011, reason="Internal Server Error")
            return False

        for channel in list(self._subscriptions.values()):
            await channel.on_exit()

        if self._disconnect_cb:
            await self._disconnect_cb(self._socket)

        if self._socket.dual_connected:
            await self._socket.close()
        return exc_type in (WebSocketDisconnect, SockRejectedError)

    async def message_loop(self):
        while True:
            msg_env = await self._socket.receive_message()
            async with self._resolver.ascope() as asc:
                await self.handle_message(msg_env, asc)

    def create_channel(
        self,
        topic: str,
        channel_faq: ChannelFactory[ChannelBase],
        resolver: Resolver,
    ) -> ChannelBase:
        channel = channel_faq.channel_type(
            topic=topic,
            socket=self._socket,
            bus=self._bus,
            resolver=resolver,
        )
        return channel

    async def _handle_join_event(self, msg: MessageEnvelope, resolver: Resolver):
        if msg.topic in self._subscriptions:
            return

        for faq in self._channel_factories:
            if (params := faq.extract_topic_params(msg.topic)) is None:
                continue
            channel = self.create_channel(msg.topic, faq, resolver)
            await channel.on_join(**params)  # inject topic params here
            self._subscriptions[msg.topic] = channel
        else:
            await self._socket.send_json(TOPIC_NOT_FOUND)

    async def _handle_exit_event(self, msg: MessageEnvelope, resolver: Resolver):
        if msg.topic not in self._subscriptions:
            await self._socket.send_json(TOPIC_NOT_FOUND)
            return

        channel = self._subscriptions.pop(msg.topic)
        await channel.on_exit()

    async def _handle_user_event(self, msg: MessageEnvelope, resolver: Resolver):
        if msg.topic not in self._subscriptions:
            await self._socket.send_json(TOPIC_NOT_FOUND)
            return

        channel = self._subscriptions[msg.topic]
        if (reply := await channel.on_message(msg)) is not None:
            data = encode(reply)
            await self._socket.send_bytes(data)

    async def handle_message(self, msg: MessageEnvelope, resolver: Resolver):
        match msg.event:
            case "join":
                await self._handle_join_event(msg, resolver)
            case "exit":
                await self._handle_exit_event(msg, resolver)
            case _:
                await self._handle_user_event(msg, resolver)


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
        self.graph.node(channel_cls)

        channel_dep = self.graph.nodes[channel_cls]
        channel_type = cast(type[ChannelBase], channel_dep.dependent)
        channel_faq = cast(Callable[..., ChannelBase], channel_dep.factory)

        factory = ChannelFactory(
            topic_pattern=channel_type.topic,
            channel_type=channel_type,
            channel_factory=channel_faq,
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
            ss = SocketSession(
                socket,
                bus,
                asc,
                self._channel_factories,
                self._on_connect,
                self._on_disconnect,
            )
            exc: Exception | None = None
            exc_cls = type(exc)

            try:
                await ss.__aenter__()
                yield ss
            except SockRejectedError:
                pass
            except Exception as exc:
                raise
            finally:
                tb = None if not isinstance(exc, Exception) else exc.__traceback__
                await ss.__aexit__(exc_cls, exc, tb)

    async def handle_connection(
        self, scope: IScope, receive: IReceive, send: ISend
    ) -> None:
        if scope["type"] != "websocket":
            raise RuntimeError(
                f"Non-websocket request sent to websocket route {self.path}"
            )

        async with self.create_socket_session(scope, receive, send) as ss:
            await ss.message_loop()
