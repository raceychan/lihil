from lihil import Payload, Resp, Route, status
from lihil.plugins.bus import BusFactory, EventBus, MessageRegistry
from lihil.plugins.testing import LocalClient


class Event(Payload): ...


class TodoCreated(Event):
    name: str
    content: str


registry = MessageRegistry(event_base=Event)


@registry.register
async def listen_create(created: TodoCreated):
    print(f"received {created}")


bus_factory = BusFactory(registry)
bus_route = Route("/bus", busmaker=bus_factory)


@bus_route.post
async def create_todo(name: str, content: str, bus: EventBus) -> Resp[None, status.OK]:
    await bus.publish(TodoCreated(name, content))


async def test_bus_is_singleton():
    ep = bus_route.get_endpoint("POST")
    assert ep.deps.singletons
    assert ep.deps.singletons[0][1].type_ is EventBus


async def test_call_ep_invoke_bus():
    ep = bus_route.get_endpoint("POST")
    client = LocalClient()
    await client.call_endpoint(ep, query_params=dict(name="1", content="2"))
