from pathlib import Path

from msgspec import Struct
from msgspec.json import decode, encode

from lihil import Lihil, Route, WebSocket, WebSocketRoute
from lihil.vendors import Response, WebSocketDisconnect

BASE_DIR = Path(__file__).resolve().parent
CHAT_HTML = BASE_DIR / "chat.html"

page = Route("/")
ws_route = WebSocketRoute("/ws/chat")

active_peers: set[WebSocket] = set()


class Message(Struct, kw_only=True):
    name: str = "anonymous"
    text: str = ""
    sentAt: str

    def to_json(self) -> str:
        return encode(self).decode()

    @classmethod
    def from_json(cls, val: str):
        return decode(val, type=cls)


async def broadcast(msg: Message) -> None:
    """Send message to all active peers, pruning any closed connections."""
    dead: set[WebSocket] = set()
    for peer in active_peers:
        await peer.send_text(msg.to_json())
    active_peers.difference_update(dead)


@page.get
async def serve_chat() -> Response:
    return Response(CHAT_HTML.read_bytes(), media_type="text/html")


@ws_route.ws_handler
async def chat_socket(ws: WebSocket) -> None:
    await ws.accept()
    active_peers.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            message = Message.from_json(raw)
            await broadcast(message)
    except WebSocketDisconnect:
        print(f"{ws} got disconnected")
        active_peers.discard(ws)


app = Lihil(page, ws_route)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
