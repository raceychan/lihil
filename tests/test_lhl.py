from contextlib import asynccontextmanager

from lihil import HTTPException, Lihil, Payload, Route
from lihil.lihil import AppState


class AppTestState(AppState):
    value: str = "test"


@asynccontextmanager
async def my_lifespan(app: Lihil[AppTestState]):
    yield app.app_state


class SamplePayload(Payload):
    name: str
    value: int


class CustomError(HTTPException[str]):
    __status__ = 400


def test_lihil_init():
    """Test basic Lihil initialization with different parameters"""
    # Test with minimal parameters
    app = Lihil[AppTestState]()
    assert app is not None

    # Test with routes
    route = Route("test")
    app = Lihil(routes=[route])

    assert route in app.routes
