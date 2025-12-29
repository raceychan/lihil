import pytest
from starlette.testclient import TestClient

from lihil import Lihil, WebSocketRoute
from lihil.channel import EVENT_NOT_FOUND, ISocket, TOPIC_NOT_FOUND
from lihil.websocket import WSManagedEndpoint


async def noop():
    return None


def test_managed_ws_flow_with_pending():
    route = WebSocketRoute("/ws")
    room = route.channel("room:{id}")
    events: list[str] = []

    @route.on_connect
    async def on_connect(sock: ISocket, **_):
        events.append("connect")

    @route.on_disconnect
    async def on_disconnect(sock: ISocket, **_):
        events.append("disconnect")

    @room.on_join
    async def on_join(params, sock: ISocket):
        events.append(f"join:{params.get('id')}")

    @room.on_exit
    async def on_exit(sock: ISocket):
        events.append("exit")

    @room.on_receive("ping")
    async def on_ping(payload, sock: ISocket):
        await sock.reply({"pong": payload})

    route.handler(noop)

    app = Lihil(route)
    app._setup()
    assert isinstance(route._ws_ep, WSManagedEndpoint)

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json({"topic": "room:123", "event": "join"})
        ws.send_json({"topic": "room:123", "event": "ping", "payload": "hi"})
        msg = ws.receive_json()
        assert msg == {"topic": "room:123", "event": "reply", "payload": {"pong": "hi"}}

    # order: connect -> join -> exit -> disconnect
    assert events[0] == "connect"
    assert "join:123" in events
    assert "exit" in events
    assert events[-1] == "disconnect"


def test_unknown_topic_sends_error():
    route = WebSocketRoute("/ws")
    route.handler(noop)
    app = Lihil(route)
    app._setup()

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json({"topic": "missing", "event": "join"})
        assert ws.receive_json() == TOPIC_NOT_FOUND


def test_unknown_event_sends_error():
    route = WebSocketRoute("/ws")
    room = route.channel("room:{id}")

    @room.on_join
    async def on_join(params, sock: ISocket):
        # no-op join
        return None

    route.handler(noop)
    app = Lihil(route)
    app._setup()

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json({"topic": "room:1", "event": "join"})
        ws.send_json({"topic": "room:1", "event": "unknown"})
        assert ws.receive_json() == EVENT_NOT_FOUND
