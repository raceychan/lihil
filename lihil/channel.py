import re
from typing import Any, Awaitable, Callable, Protocol

from lihil.interface import IReceive, IScope, ISend, Record, field
from lihil.vendors import WebSocket, WebSocketState

PublishFunc = Callable[[str, str, Any], Awaitable[None]]


class OnJoinCallback(Protocol):
    async def __call__(self, params: dict[str, Any], sock: "ISocket") -> Any: ...


class OnExitCallback(Protocol):
    async def __call__(self, sock: "ISocket") -> Any: ...


class OnReceiveCallback(Protocol):
    async def __call__(self, payload: Any, sock: "ISocket") -> Any: ...


class RejectError(Exception):
    """Raised when a socket is rejected before accept."""


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


class ISocket:
    """
    Composition wrapper around starlette's WebSocket.
    Exposes a curated API surface plus channel helpers.
    """

    def __init__(
        self,
        scope: IScope,
        receive: IReceive,
        send: ISend,
        *,
        topic: str | None = None,
        params: dict[str, Any] | None = None,
        assigns: dict[str, Any] | None = None,
    ):
        self._ws = WebSocket(scope, receive, send)
        self.topic = topic
        self.params = params or {}
        self.assigns = assigns or {}
        self._publish: PublishFunc | None = None

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

    async def reply(self, payload: Any, event: str = "reply") -> None:
        await self._ws.send_json(
            {"topic": self.topic, "event": event, "payload": payload}
        )

    async def emit(self, payload: Any, event: str = "emit") -> None:
        await self._ws.send_json(
            {"topic": self.topic, "event": event, "payload": payload}
        )

    async def publish(self, payload: Any, event: str = "broadcast") -> None:
        if not self._publish or not self.topic:
            raise RuntimeError("publish backend or topic not set")
        await self._publish(self.topic, event, payload)

    async def allow_if(
        self, condition: bool, code: int = 4403, reason: str = "Forbidden"
    ):
        if not condition:
            await self._ws.close(code=code, reason=reason)
            raise RejectError("connection rejected")


TOPIC_NOT_FOUND = {"code": 4404, "reason": "Topic not found"}
EVENT_NOT_FOUND = {"code": 4404, "reason": "Event not found"}


async def _default_on_join(params: dict[str, Any], sock: ISocket) -> None:
    return None


async def _default_on_exit(sock: ISocket) -> None:
    return None


class Channel:
    """
    Topic-scoped callbacks. Matching/dispatch will live in managed websocket.
    """

    def __init__(self, topic_pattern: str):
        self.topic_pattern = topic_pattern
        self._regex = self._compile_topic_pattern(topic_pattern)

        self._on_join: OnJoinCallback = _default_on_join
        self._on_exit: OnExitCallback = _default_on_exit
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
    def on_join_callback(self) -> OnJoinCallback:
        return self._on_join

    @property
    def on_exit_callback(self) -> OnExitCallback:
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
