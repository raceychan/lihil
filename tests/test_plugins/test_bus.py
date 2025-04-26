from typing import Any
import pytest

from lihil import Resp, Route, status
from lihil.plugins.bus import Event, EventBus
from lihil.plugins.testclient import LocalClient


class TodoCreated(Event):
    name: str
    content: str


async def listen_create(created: TodoCreated, _: Any, bus: EventBus):
    assert created.name
    assert created.content
    assert isinstance(bus, EventBus)


async def listen_twice(created: TodoCreated, _: Any):
    assert created.name
    assert created.content


@pytest.fixture
def bus_route():
    return Route("/bus", listeners=[listen_create, listen_twice])


async def test_bus_is_singleton(bus_route: Route):
    async def create_todo(
        name: str, content: str, bus: EventBus
    ) -> Resp[None, status.OK]:
        await bus.publish(TodoCreated(name, content))

    bus_route.post(create_todo)

    ep = bus_route.get_endpoint("POST")
    ep.setup()
    assert ep.sig.plugins
    assert any(p.type_ is EventBus for p in ep.sig.plugins.values())


async def test_call_ep_invoke_bus(bus_route: Route):
    async def create_todo(
        name: str, content: str, bus: EventBus
    ) -> Resp[None, status.OK]:
        await bus.publish(TodoCreated(name, content))

    bus_route.post(create_todo)
    ep = bus_route.get_endpoint("POST")
    client = LocalClient()
    await client.call_endpoint(ep, query_params=dict(name="1", content="2"))
