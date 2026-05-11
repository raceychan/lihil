from pathlib import Path
from typing import Any

from msgspec import Struct

from lihil import ChannelBase, ISocket, Lihil, Route, SocketHub, Topic
from lihil.vendors import Response

BASE_DIR = Path(__file__).resolve().parent
CHAT_HTML = BASE_DIR / "chat.html"

page = Route("/")
chat_hub = SocketHub("/ws/chat")


class Message(Struct, kw_only=True):
    name: str = "anonymous"
    text: str = ""
    sentAt: str

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "text": self.text, "sentAt": self.sentAt}


@page.get
async def serve_chat() -> Response:
    return Response(CHAT_HTML.read_bytes(), media_type="text/html")


@chat_hub.on_connect
async def on_connect(sock: ISocket) -> None:
    # Simple per-socket bookkeeping example; not required by the hub.
    sock.state.setdefault("rooms", set())


@chat_hub.on_disconnect
async def on_disconnect(sock: ISocket) -> None:
    sock.state.get("rooms", set()).clear()


class RoomChannel(ChannelBase):
    topic = Topic("room:{room_id}")

    async def on_join(self, room_id: str = "lobby") -> None:
        await super().on_join()
        self.socket.state.setdefault("rooms", set()).add(room_id)
        await self.emit({"room": room_id, "event": "joined"}, event="system")

    async def on_exit(self) -> None:
        await super().on_exit()
        room_id = self.resolved_topic.removeprefix("room:")
        self.socket.state.get("rooms", set()).discard(room_id)
        await self.emit({"room": room_id, "event": "left"}, event="system")

    async def on_chat(self, payload: dict[str, Any]) -> None:
        message = Message(**payload)
        await self.publish(message.to_payload(), event="chat")


chat_hub.channel(RoomChannel)


app = Lihil(page, chat_hub)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
