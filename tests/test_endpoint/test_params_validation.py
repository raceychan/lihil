from typing import Any

import pytest
from ididi import Graph

from lihil.interface import Payload
from lihil.interface.marks import Annotated
from lihil.signature import EndpointParser, EndpointSignature, Param


async def get_order(
    user_id: str,
    order_id: str,
    limit: int,
    x_token: Annotated[str, Param("header", alias="x-token")],
) -> dict[str, str]: ...


class User(Payload):
    id: int
    name: str
    email: str


async def create_user(user: User) -> User: ...


@pytest.fixture
def get_order_dep() -> EndpointSignature[Any]:
    dg = Graph()
    path = "/users/{user_id}/orders/{order_id}"
    dep = EndpointParser(dg, path).parse(get_order)
    return dep


@pytest.fixture
def create_user_dep() -> EndpointSignature[Any]:
    dg = Graph()
    path = "/user"
    dep = EndpointParser(dg, path).parse(create_user)
    return dep
