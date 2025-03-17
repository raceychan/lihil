from types import UnionType

from lihil import Payload, status
from lihil.interface.marks import Json, Resp, is_resp_mark
from lihil.routing import Route


def test_validate_mark():
    assert is_resp_mark(Resp[Json[str], status.OK])


class User(Payload):
    name: str
    age: int


class Order(Payload):
    id: str
    price: float


async def get_order(
    user_id: str, order_id: str, q: int, l: str, u: User
) -> Order | str: ...


def test_endpoint_deps():
    route = Route()
    route.get(get_order)
    ep = route.get_endpoint("GET")
    rt = ep.deps.return_param
    assert isinstance(rt.type_, UnionType)
    # assert str in rt.type_
    # assert Order in rt.type_
