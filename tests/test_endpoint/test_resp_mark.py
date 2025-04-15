from typing import Union

import pytest

from lihil import Payload, status, Header
from lihil.interface.marks import Json, Resp, is_resp_mark, resp_mark, param_mark, lhl_get_origin
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
    ep.setup()
    rt = ep.sig.return_params[200]
    assert rt.type_ == Union[Order, str]



def test_lhl_get_origin():
    ori = lhl_get_origin(Header[str])
    assert ori is Header

def test_resp_param_mark_idenpotent():

    ret_mark = resp_mark("test")
    assert resp_mark(ret_mark) is ret_mark

    pmark = param_mark("test")
    assert param_mark(pmark) is pmark
