import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from ididi import Graph

from lihil.ds import ISocket, SockRejectedError, SubscriberCallback
from lihil.interface import (
    ASGIApp,
    IAsyncFunc,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    Record,
    field,
)
from lihil.routing import RouteBase
from lihil.vendors import WebSocketDisconnect, WebSocketState


class OnJoinCallback(Protocol):
    async def __call__(self, params: dict[str, Any], sock: "ISocket") -> Any: ...


class OnExitCallback(Protocol):
    async def __call__(self, sock: "ISocket") -> Any: ...


class OnReceiveCallback(Protocol):
    async def __call__(self, payload: Any, sock: "ISocket") -> Any: ...


class MessageEnvelope(Record):
    topic: str
    event: str
    payload: Any = None
    topic_params: dict[str, str] = field(default_factory=dict[str, str])

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "MessageEnvelope":
        try:
            topic = raw["topic"]
            event = raw["event"]
            payload = raw.get("payload")
        except Exception as exc:
            raise ValueError(f"Invalid message envelope: {raw}") from exc
        return cls(topic=topic, event=event, payload=payload)


TOPIC_NOT_FOUND = {"code": 4404, "reason": "Topic not found"}
EVENT_NOT_FOUND = {"code": 4404, "reason": "Event not found"}


class Channel:
    """
    Topic-scoped callbacks. Matching/dispatch will live in managed websocket.
    """

    def __init__(self, topic_pattern: str):
        self.topic_pattern = topic_pattern
        self._regex = self._compile_topic_pattern(topic_pattern)

        self._on_join: OnJoinCallback | None = None
        self._on_exit: OnExitCallback | None = None
        self._on_receive: dict[str, OnReceiveCallback] = {}

    def on_join(self, func: OnJoinCallback) -> OnJoinCallback:
        self._on_join = func
        return func

    def on_exit(self, func: OnExitCallback) -> OnExitCallback:
        self._on_exit = func
        return func

    def on_receive(self, event: str):
        def decorator(func: OnReceiveCallback):
            self._on_receive[event] = func
            return func

        return decorator

    @property
    def on_join_callback(self) -> OnJoinCallback | None:
        return self._on_join

    @property
    def on_exit_callback(self) -> OnExitCallback | None:
        return self._on_exit

    @property
    def on_receive_callbacks(
        self,
    ) -> dict[str, OnReceiveCallback]:
        return self._on_receive

    def _compile_topic_pattern(self, pattern: str) -> re.Pattern[str]:
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

    def match(self, topic: str) -> dict[str, str] | None:
        if m := self._regex.match(topic):
            return m.groupdict()
        return None

    async def dispatch(self, env: MessageEnvelope, sock: ISocket) -> None:
        handler = self._on_receive.get(env.event)
        if handler:
            await handler(env.payload, sock)
        else:
            await sock.send_json(EVENT_NOT_FOUND)


class SocketBus(Protocol):
    """
    Callback-based pubsub for websockets.
    """

    async def subscribe(self, topic: str, callback: SubscriberCallback) -> None: ...

    async def unsubscribe(self, topic: str, callback: SubscriberCallback) -> None: ...

    async def publish(self, topic: str, event: str, payload: Any) -> None: ...


class InMemorySocketBus(SocketBus):
    def __init__(self):
        self._subs: dict[str, set[SubscriberCallback]] = defaultdict(set)

    async def subscribe(self, topic: str, callback: SubscriberCallback) -> None:
        self._subs[topic].add(callback)

    async def unsubscribe(self, topic: str, callback: SubscriberCallback) -> None:
        callbacks = self._subs.get(topic)
        if not callbacks:
            return
        callbacks.discard(callback)
        if not callbacks:
            self._subs.pop(topic, None)

    async def publish(self, topic: str, event: str, payload: Any) -> None:
        callbacks = self._subs.get(topic)
        if not callbacks:
            return

        message = MessageEnvelope(topic=topic, event=event, payload=payload)
        stale: set[SubscriberCallback] = set()
        for cb in list(callbacks):
            try:
                await cb(message)
            except Exception:
                stale.add(cb)
        if stale:
            callbacks.difference_update(stale)
        if not callbacks:
            self._subs.pop(topic, None)


class SocketHub(RouteBase):
    call_stack: ASGIApp | None = None

    def __init__(
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        bus: SocketBus | None = None,
    ):
        super().__init__(path, graph=graph, middlewares=middlewares)
        self._on_connect: IAsyncFunc[..., None] | None = None
        self._on_disconnect: IAsyncFunc[..., None] | None = None
        self._channels: list[Channel] = []
        self._bus: SocketBus = bus or InMemorySocketBus()
        self.call_stack: ASGIApp | None = None

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if not self.call_stack:
            raise RuntimeError(f"{self.__class__.__name__}({self._path}) not setup")
        await self.call_stack(scope, receive, send)

    def channel(self, pattern: str) -> Channel:
        ch = Channel(pattern)
        self._channels.append(ch)
        self._channels.sort(key=lambda c: c.topic_pattern.count("{"), reverse=True)
        return ch

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
        self.call_stack = self.chainup_middlewares(self._dispatch)
        self._is_setup = True

    async def _dispatch(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if scope["type"] != "websocket":
            raise RuntimeError("SocketHub only handles websocket scope")

        sock = ISocket(scope, receive, send)
        sock._publish = self._bus.publish  # type: ignore[attr-defined]

        subscriptions: dict[str, tuple[Channel, SubscriberCallback]] = {}

        try:
            if self._on_connect:
                await self._on_connect(sock)

            await sock.accept()

            while True:
                env = MessageEnvelope.from_raw(await sock.receive_json())
                channel, params = self._match_channel(env.topic)
                if not channel or params is None:
                    await sock.send_json(TOPIC_NOT_FOUND)
                    continue

                sock.topic, sock.params = env.topic, params
                env.topic_params.update(params)

                if env.event == "join":
                    if env.topic not in subscriptions:
                        if channel.on_join_callback:
                            await channel.on_join_callback(env.topic_params, sock)
                        await self._bus.subscribe(env.topic, sock.on_message)
                        subscriptions[env.topic] = (channel, sock.on_message)
                    continue

                if env.event == "leave":
                    subscribed = subscriptions.pop(env.topic, None)
                    if not subscribed:
                        await sock.send_json(TOPIC_NOT_FOUND)
                        continue
                    sub_channel, cb = subscribed
                    await self._bus.unsubscribe(env.topic, cb)
                    if sub_channel.on_exit_callback:
                        await sub_channel.on_exit_callback(sock)
                    continue

                if env.topic not in subscriptions:
                    await sock.send_json(TOPIC_NOT_FOUND)
                    continue

                await channel.dispatch(env, sock)
        except WebSocketDisconnect:
            pass
        except SockRejectedError:
            pass
        except Exception:
            if sock.client_state == WebSocketState.CONNECTED:
                await sock.close(code=1011, reason="Internal Server Error")
            raise
        finally:
            for topic, (channel, cb) in subscriptions.items():
                try:
                    await self._bus.unsubscribe(topic, cb)
                finally:
                    if channel.on_exit_callback:
                        await channel.on_exit_callback(sock)

            if self._on_disconnect:
                await self._on_disconnect(sock)
            if (
                sock.application_state == WebSocketState.CONNECTED
                and sock.client_state == WebSocketState.CONNECTED
            ):
                await sock.close()

    def _match_channel(
        self, topic: str
    ) -> tuple[Channel | None, dict[str, str] | None]:
        for ch in self._channels:
            if params := ch.match(topic):
                return ch, params
        return None, None
