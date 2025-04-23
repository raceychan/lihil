from lihil.websocket import WebSocketRoute, WebSocket
from lihil import LocalClient, Lihil



async def test_ws():
    lc = LocalClient()

    ws = WebSocketRoute("test")
    async def test_ws(ws: WebSocket):
        await ws.accept()

    lhl = Lihil()
    lhl.include_routes(ws)
