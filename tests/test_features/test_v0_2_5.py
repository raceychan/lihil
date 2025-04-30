from typing import TypedDict

import pytest

from lihil import Graph, Lihil, LocalClient, Route
from lihil.interface.marks import AppState
from lihil.signature import EndpointParser
from lihil.signature.params import StateParam

app_state = {}


def test_app_state():
    parser = EndpointParser(Graph(), "test")

    async def create_user(name: AppState[str]): ...

    res = parser.parse(create_user)
    param = res.states["name"]
    assert isinstance(param, StateParam)


class MyState(TypedDict):
    name: str


async def test_ep_with_app_state():

    route = Route("/test")

    async def f(name: AppState[str]):
        assert name == "lihil"

    route.get(f)

    mystate = MyState(name="lihil")
    lhl = Lihil[MyState](routes=[route])

    lhl._app_state = mystate  # type: ignore

    lc = LocalClient()
    res = await lc.call_app(lhl, "GET", "/test")
    assert res.status_code == 200


async def test_ep_requires_app_state_but_not_set():

    route = Route("/test")

    async def f(name: AppState[str]):
        assert name == "lihil"

    route.get(f)

    lhl = Lihil[None](routes=[route])

    lc = LocalClient()
    with pytest.raises(ValueError):
        await lc.call_app(lhl, "GET", "/test")
