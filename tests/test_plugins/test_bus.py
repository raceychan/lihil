from typing import Any, get_origin

import pytest

from lihil import Annotated, Route, status
from lihil.ds.event import Event
from lihil.plugins.bus import (
    BusPlugin,
    BusTerminal,
    EventBus,
    MessageRegistry,
    PEventBus,
)
from lihil.local_client import LocalClient


class TodoCreated(Event):
    name: str
    content: str


async def listen_create(created: TodoCreated, _: Any, bus: EventBus[Any]):
    assert created.name
    assert created.content
    assert isinstance(bus, EventBus)


async def listen_twice(created: TodoCreated, _: Any):
    assert created.name
    assert created.content


@pytest.fixture
async def bus_route():
    route = Route("/bus")
    await route.setup()
    return route


@pytest.fixture
def registry():
    registry = MessageRegistry(event_base=Event)
    registry.register(listen_create, listen_twice)
    return registry


async def test_bus_is_singleton(bus_route: Route):
    async def create_todo(
        name: str, content: str, bus: PEventBus
    ) -> Annotated[None, status.OK]:
        await bus.publish(TodoCreated(name, content))

    bus_route.post(create_todo)

    ep = bus_route.get_endpoint("POST")
    await bus_route.setup()
    assert ep.sig.plugins
    assert get_origin(ep.sig.plugins["bus"].type_) is EventBus


async def test_call_ep_invoke_bus(bus_route: Route, registry: MessageRegistry[Event]):
    async def create_todo(
        name: str, content: str, bus: PEventBus
    ) -> Annotated[None, status.OK]:
        await bus.publish(TodoCreated(name, content))

    bus_route.post(create_todo, plugins=[BusPlugin(BusTerminal(registry)).decorate])
    ep = bus_route.get_endpoint("POST")
    await bus_route.setup()
    client = LocalClient()
    resp = await client.call_endpoint(ep, query_params=dict(name="1", content="2"))

    assert resp.status_code == 200
