from typing import Any, get_origin

import pytest

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

from lihil import Annotated, Route, status, use
from msgspec import Struct
from lihil.local_client import LocalClient
from lihil.plugins.bus import (
    BusPlugin,
    BusTerminal,
    EventBus,
    MessageRegistry,
    PEventBus,
)


class Event(Struct):
    pass


class TodoCreated(Event):
    name: str
    content: str


async def listen_create(created: TodoCreated, _: Any, bus: Annotated[EventBus[Any], use(EventBus, reuse=True)]):
    assert created.name
    assert created.content
    assert isinstance(bus, EventBus)


async def listen_twice(created: TodoCreated, _: Any):
    assert created.name
    assert created.content


@pytest.fixture
async def bus_route():
    route = Route("/bus")
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
    assert ep.sig.plugins
    assert get_origin(ep.sig.plugins["bus"].type_) is EventBus


async def test_call_ep_invoke_bus(bus_route: Route, registry: MessageRegistry[Event]):
    async def create_todo(
        name: str, content: str, bus: PEventBus
    ) -> Annotated[None, status.OK]:
        await bus.publish(TodoCreated(name, content))

    bus_route.post(create_todo, plugins=[BusPlugin(BusTerminal(registry)).decorate])
    ep = bus_route.get_endpoint("POST")
    client = LocalClient()
    resp = await client.call_endpoint(ep, query_params=dict(name="1", content="2"))

    assert resp.status_code == 200
