from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict

from msgspec import Struct

from lihil import ISocket, Lihil, Route, WebSocketRoute
from lihil.vendors import Response

BASE_DIR = Path(__file__).resolve().parent
CHAT_HTML = BASE_DIR / "chat.html"

page = Route("/")
ws_route = WebSocketRoute("/ws/chat")
room_channel = ws_route.channel("room:{room_id}")

# Naive in-memory pubsub for demo: room_id -> sockets
rooms: DefaultDict[str, set[ISocket]] = defaultdict(set)


class Message(Struct, kw_only=True):
    name: str = "anonymous"
    text: str = ""
    sentAt: str

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "text": self.text, "sentAt": self.sentAt}


async def broadcast(room_id: str, payload: dict[str, Any]) -> None:
    peers = rooms.get(room_id)
    if not peers:
        return
    dead: set[ISocket] = set()
    for peer in list(peers):
        try:
            await peer.send_json(
                {"topic": f"room:{room_id}", "event": "chat", "payload": payload}
            )
        except Exception:
            dead.add(peer)
    peers.difference_update(dead)


@page.get
async def serve_chat() -> Response:
    return Response(CHAT_HTML.read_bytes(), media_type="text/html")


@ws_route.on_connect
async def on_connect(sock: ISocket) -> None:
    # placeholder for auth/assigns; accept handled by framework after this hook
    sock.assigns.setdefault("rooms", set())


@ws_route.on_disconnect
async def on_disconnect(sock: ISocket) -> None:
    # ensure socket is removed from any rooms on disconnect
    for room_id in list(rooms.keys()):
        rooms[room_id].discard(sock)


@room_channel.on_join
async def on_join(params: dict[str, Any], sock: ISocket) -> None:
    room_id = params.get("room_id", "lobby")
    rooms[room_id].add(sock)
    sock.assigns.setdefault("rooms", set()).add(room_id)


@room_channel.on_exit
async def on_exit(sock: ISocket) -> None:
    for room_id in list(sock.assigns.get("rooms", set())):
        rooms[room_id].discard(sock)
    sock.assigns["rooms"] = set()


@room_channel.on_receive("chat")
async def on_chat(payload: dict[str, Any], sock: ISocket) -> None:
    room_id = sock.params.get("room_id") or "lobby"
    message = Message(**payload)
    await broadcast(room_id, message.to_payload())


@ws_route.handler
async def handle_ws() -> None:
    # managed websocket handler marker; logic lives in hooks above
    return None


app = Lihil(page, ws_route)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
