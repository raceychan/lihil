import json
from pathlib import Path

from lihil import Lihil, Route, WebSocket, WebSocketRoute
from lihil.vendors import Response

BASE_DIR = Path(__file__).resolve().parent
CHAT_HTML = BASE_DIR / "chat.html"

page = Route("/")
ws_route = WebSocketRoute("/ws/chat")

active_peers: set[WebSocket] = set()


def _safe_dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


async def broadcast(payload: dict) -> None:
    """Send message to all active peers, pruning any closed connections."""
    dead: set[WebSocket] = set()
    msg = _safe_dump(payload)
    for peer in active_peers:
        try:
            await peer.send_text(msg)
        except Exception:
            dead.add(peer)
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
            try:
                data = json.loads(raw)
            except Exception:
                data = {"text": raw}

            payload = {
                "name": data.get("name") or "anonymous",
                "text": data.get("text") or "",
                "sentAt": data.get("sentAt"),
            }
            await broadcast(payload)
    finally:
        active_peers.discard(ws)
        await ws.close()


app = Lihil(page, ws_route)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
