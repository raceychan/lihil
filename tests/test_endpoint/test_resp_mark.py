from typing import Union

import pytest

from lihil import Payload
from lihil.interface.marks import resp_mark
from lihil.routing import Route


class User(Payload):
    name: str
    age: int


class Order(Payload):
    id: str
    price: float


async def get_order(
    user_id: str, order_id: str, q: int, l: str, u: User
) -> Order | str: ...


async def test_endpoint_deps():
    route = Route()
    route.get(get_order)
    ep = route.get_endpoint("GET")
    await route.setup()
    rt = ep.sig.return_params[200]
    assert rt.type_ == Union[Order, str]


def test_resp_param_mark_idenpotent():

    ret_mark = resp_mark("test")
    assert resp_mark(ret_mark) is ret_mark
