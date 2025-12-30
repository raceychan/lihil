from typing import Any, Awaitable, Callable, Protocol

from lihil.interface import IReceive, IScope, ISend
from lihil.vendors import WebSocket, WebSocketState
from lihil.errors import SockRejectedError

PublishFunc = Callable[[str, str, Any], Awaitable[None]]





class PubSubMessage(Protocol):
    topic: str
    event: str
    payload: Any


SubscriberCallback = Callable[[PubSubMessage], Awaitable[None]]


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

    async def on_message(self, message: PubSubMessage):
        await self.send_json(
            {
                "topic": message.topic,
                "event": message.event,
                "payload": message.payload,
            }
        )

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
            raise SockRejectedError("connection rejected")
