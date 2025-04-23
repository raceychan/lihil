import pytest

from lihil import Lihil
from lihil.vendors import TestClient
from lihil.websocket import WebSocket, WebSocketRoute


async def test_ws():

    ws_route = WebSocketRoute("web_socket")

    async def test_ws(ws: WebSocket):
        await ws.accept()
        await ws.send_text("Hello, world!")
        await ws.close()

    ws_route.socket(test_ws)

    lhl = Lihil[None]()
    lhl.include_routes(ws_route)

    client = TestClient(lhl)
    client.__enter__()
    with client.websocket_connect("/web_socket") as websocket:
        data = websocket.receive_text()
        assert data == "Hello, world!"
