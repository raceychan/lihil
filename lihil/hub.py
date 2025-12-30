import asyncio
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable

from ididi import Graph
from ididi.interfaces import IDependent
from msgspec.json import Decoder, encode

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
from lihil.routing import RouteBase
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

    def __init__(
        self,
        websocket: WebSocket,
        *,
        topic: str | None = None,
        params: dict[str, Any] | None = None,
        assigns: dict[str, Any] | None = None,
    ):
        self._ws = websocket
        self.topic = topic
        self.params = params or {}
        self.assigns = assigns or {}

    @property
    def websocket(self) -> WebSocket:
        return self._ws

    @property
    def application_state(self) -> WebSocketState:
        return self._ws.application_state

    @property
    def client_state(self) -> WebSocketState:
        return self._ws.client_state

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

    async def reply(self, payload: Any, event: str = "reply") -> None:
        await self._ws.send_json(
            {"topic": self.topic, "event": event, "payload": payload}
        )

    async def emit(self, payload: Any, event: str = "emit") -> None:
        await self._ws.send_json(
            {"topic": self.topic, "event": event, "payload": payload}
        )

    async def allow_if(
        self, condition: bool, code: int = 4403, reason: str = "Forbidden"
    ):
        if not condition:
            await self._ws.close(code=code, reason=reason)
            raise SockRejectedError("connection rejected")


class SocketBus(ABC):
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
        self,
        socket: ISocket,
        *,
        topic: str,
        params: dict[str, str] | None = None,
        bus: SocketBus,
        graph: Graph,
    ):
        self.socket = socket
        self.bus = bus
        self.graph = graph
        self._resolved_topic = topic
        self.params = params or {}

    @property
    def resolved_topic(self) -> str:
        return self._resolved_topic

    @classmethod
    def match(cls, topic: str) -> dict[str, str] | None:
        if m := cls.topic.match(topic):
            return m.groupdict()
        return None

    async def publish(self, payload: Any, *, event: str = "broadcast") -> None:
        await self.bus.publish(self._resolved_topic, event, payload)

    async def broadcast(self, payload: Any, *, event: str = "broadcast") -> None:
        # Alias for publish to keep terminology consistent.
        await self.publish(payload, event=event)

    async def on_update(self, env: MessageEnvelope) -> None:
        """
        Default bus subscriber callback: echoes envelope to the socket.
        """
        await self.socket.send_json(
            {"topic": env.topic, "event": env.event, "payload": env.payload}
        )

    async def on_join(self) -> None:  # pragma: no cover - to be overridden
        await self.bus.subscribe(self.resolved_topic, self.on_update)

    @abstractmethod
    async def on_message(self, env: MessageEnvelope) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def on_leave(self) -> None:  # pragma: no cover - to be overridden
        await self.bus.unsubscribe(self.resolved_topic, self.on_update)


class ChannelRegistry:
    """
    Register channel classes and produce instances for a matched topic.
    """

    def __init__(self) -> None:
        self._channels: list[type[ChannelBase]] = []

    def add_channel(self, channel_cls: type[ChannelBase]) -> type[ChannelBase]:
        self._channels.append(channel_cls)
        self._channels.sort(key=lambda cls: len(cls.topic.groupindex), reverse=True)
        return channel_cls

    def create(
        self,
        topic: str,
        *,
        socket: ISocket,
        bus: SocketBus,
        graph: Graph,
    ) -> ChannelBase | None:
        """
        Return a channel instance directly when a pattern matches.
        The caller (hub) supplies socket/bus; params are resolved here.
        """
        for ch_cls in self._channels:
            if params := ch_cls.match(topic):
                return ch_cls(socket, topic=topic, params=params, bus=bus, graph=graph)
        return None


class SocketHub(RouteBase):
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
        self._registry = ChannelRegistry()
        self._bus_factory = bus_factory
        self.graph.node(bus_factory)
        self.call_stack: ASGIApp | None = None

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if not self.call_stack:
            raise RuntimeError(f"{self.__class__.__name__}({self._path}) not setup")
        await self.call_stack(scope, receive, send)

    def channel(self, channel_cls: type[ChannelBase]) -> type[ChannelBase]:
        """
        Register a channel class. Acts as a decorator-friendly helper.
        """
        return self._registry.add_channel(channel_cls)

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
        self.call_stack = self.chainup_middlewares(self.connect)
        self._is_setup = True

    async def connect(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if scope["type"] != "websocket":
            raise RuntimeError(
                f"Non-websocket request sent to websocket route {self.path}"
            )

        sock = ISocket(WebSocket(scope, receive, send))
        subscriptions: dict[str, ChannelBase] = {}
        bus = await self.graph.aresolve(SocketBus)

        try:
            if self._on_connect:
                await self._on_connect(sock)

            await sock.accept()
            while True:
                msg_env = await sock.receive_message()
                if msg_env.event == "join":
                    if msg_env.topic in subscriptions:
                        continue

                    channel = self._registry.create(
                        msg_env.topic, socket=sock, bus=bus, graph=self.graph
                    )
                    if not channel:
                        await sock.send_json(TOPIC_NOT_FOUND)
                        continue

                    await channel.on_join()
                    subscriptions[msg_env.topic] = channel
                    continue
                elif msg_env.event == "leave":
                    channel = subscriptions.pop(msg_env.topic, None)
                    if not channel:
                        await sock.send_json(TOPIC_NOT_FOUND)
                        continue

                    await channel.on_leave()
                    continue
                else:
                    channel = subscriptions.get(msg_env.topic)
                    if not channel:
                        await sock.send_json(TOPIC_NOT_FOUND)
                        continue

                    if (reply := await channel.on_message(msg_env)) is not None:
                        data = encode(reply)
                        await sock.send_bytes(data)
        except WebSocketDisconnect:
            pass
        except SockRejectedError:
            pass
        except Exception:
            if sock.client_state == WebSocketState.CONNECTED:
                await sock.close(code=1011, reason="Internal Server Error")
            raise
        finally:
            for _, channel in list(subscriptions.items()):
                await channel.on_leave()

            if self._on_disconnect:
                await self._on_disconnect(sock)
            if (
                sock.application_state == WebSocketState.CONNECTED
                and sock.client_state == WebSocketState.CONNECTED
            ):
                await sock.close()
