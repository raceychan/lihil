from lihil import Resp, Route, status
from lihil.plugins.bus import Event, EventBus
from lihil.plugins.testclient import LocalClient


class TodoCreated(Event):
    name: str
    content: str


async def listen_create(created: TodoCreated):
    assert created.name
    assert created.content


async def listen_twice(created: TodoCreated):
    assert created.name
    assert created.content


bus_route = Route("/bus", listeners=[listen_create, listen_twice])


async def test_bus_is_singleton():
    async def create_todo(
        name: str, content: str, bus: EventBus
    ) -> Resp[None, status.OK]:
        await bus.publish(TodoCreated(name, content))

    bus_route.post(create_todo)

    ep = bus_route.get_endpoint("POST")
    assert ep.deps.singletons
    assert ep.deps.singletons[0][1].type_ is EventBus


async def test_call_ep_invoke_bus():
    ep = bus_route.get_endpoint("POST")
    client = LocalClient()
    await client.call_endpoint(ep, query_params=dict(name="1", content="2"))
