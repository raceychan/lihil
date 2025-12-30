import pytest
from ididi.interfaces import AsyncResource

from lihil import (
    Annotated,
    Graph,
    Ignore,
    Lihil,
    Payload,
    WebSocket,
    WebSocketRoute,
    use,
)
from lihil.errors import RouteSetupError
from lihil.plugins.bus import BusPlugin, BusTerminal, PEventBus


async def test_ws(test_client):

    ws_route = WebSocketRoute("web_socket")

    async def test_ws(ws: WebSocket):
        await ws.accept()
        await ws.send_text("Hello, world!")
        await ws.close()

    ws_route.endpoint(test_ws)

    lhl = Lihil()
    lhl.include(ws_route)

    client = test_client(lhl)
    with client:
        with client.websocket_connect("/web_socket") as websocket:
            data = websocket.receive_text()
            assert data == "Hello, world!"


async def test_ws_starlette_socket_supported(test_client):
    ws_route = WebSocketRoute("legacy_ws")

    async def test_ws(ws: WebSocket):
        await ws.accept()
        await ws.send_text("legacy ok")
        await ws.close()

    ws_route.endpoint(test_ws)

    lhl = Lihil()
    lhl.include(ws_route)

    client = test_client(lhl)
    with client:
        with client.websocket_connect("/legacy_ws") as websocket:
            data = websocket.receive_text()
            assert data == "legacy ok"


async def test_ws_with_body_fail(test_client):

    ws_route = WebSocketRoute("web_socket")

    class WebPayload(Payload):
        name: str

    async def test_ws(ws: WebSocket, pld: WebPayload):
        await ws.accept()
        await ws.send_text("Hello, world!")
        await ws.close()

    ws_route.endpoint(test_ws)

    lhl = Lihil()
    lhl.include(ws_route)

    client = test_client(lhl)

    with pytest.raises(RouteSetupError):
        client.__enter__()


async def test_ws_full_fledge(test_client):
    ws_route = WebSocketRoute("web_socket/{session_id}")

    async def ws_factory(ws: WebSocket) -> Ignore[AsyncResource[WebSocket]]:
        await ws.accept()
        yield ws
        await ws.close()

    async def ws_handler(
        ws: Annotated[WebSocket, use(ws_factory, reuse=False)],
        session_id: str,
        max_users: int,
    ):
        assert session_id == "session123" and max_users == 5
        await ws.send_text("Hello, world!")

    ws_route.endpoint(ws_handler)

    lhl = Lihil()
    lhl.include(ws_route)

    client = test_client(lhl)
    with client:
        with client.websocket_connect(
            "/web_socket/session123?max_users=5"
        ) as websocket:
            data = websocket.receive_text()
            assert data == "Hello, world!"


async def test_ws_repr(test_client):

    ws_route = WebSocketRoute("web_socket/{session_id}")

    async def ws_handler(
        ws: WebSocket,
        session_id: str,
        max_users: int,
    ):
        assert session_id == "session123" and max_users == 5
        await ws.send_text("Hello, world!")

    ws_route.endpoint(ws_handler)

    repr(ws_route)
    repr(ws_route.endpoint)


async def test_ws_error(test_client):

    ws_route = WebSocketRoute("rt_error")

    with pytest.raises(RuntimeError):
        await ws_route(1, 2, 3)


async def test_ws_plugins(test_client):
    ws_route = WebSocketRoute("test/{session_id}")

    async def ws_handler(
        ws: WebSocket,
        bus: PEventBus,
        dg: Graph,
        session_id: str,
        max_users: int,
    ):
        await ws.accept()
        await ws.send_text("Hello, world!")
        await ws.close()

    plugin = BusPlugin(busterm=BusTerminal())
    ws_route.endpoint(ws_handler, plugins=[plugin.decorate])

    lhl = Lihil()
    lhl.include(ws_route)

    client = test_client(lhl)
    with client:
        with client.websocket_connect("/test/session123?max_users=5") as websocket:
            websocket.receive_text()


async def test_ws_close_on_exc(test_client):
    ws_route = WebSocketRoute("error/{session_id}")

    async def ws_handler(
        ws: WebSocket,
        bus: PEventBus,
        dg: Graph,
        session_id: str,
        max_users: int,
    ):
        raise Exception

    ws_route.endpoint(ws_handler)

    lhl = Lihil()
    lhl.include(ws_route)

    client = test_client(lhl)
    with client:
        with pytest.raises(Exception):
            with client.websocket_connect("/error/session123?max_users=5") as websocket:
                websocket.receive_text()


async def test_ws_with_include_subs():
    paretn_ws = WebSocketRoute("/parent")
    paretn_ws.sub("/sub")

    root_ws = WebSocketRoute("/api/v0")

    root_ws.merge(paretn_ws)
    assert root_ws.subroutes[0].path == root_ws.path + "/parent"
    assert root_ws.subroutes[0].subroutes[0].path == root_ws.path + "/parent" + "/sub"
