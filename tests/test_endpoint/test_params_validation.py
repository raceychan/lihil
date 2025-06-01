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


# def test_prepare_params(get_order_dep: EndpointSignature[Any]):
#     user_id = "u11b22"
#     order_id = "o22d33"
#     token = "token"

#     req_path = dict(user_id=user_id, order_id=order_id)
#     req_query = dict(limit="5")
#     req_header = {"x-token": token}

#     parsed = get_order_dep.prepare_params(
#         req_path=req_path, req_query=req_query, req_header=req_header
#     )

#     assert not parsed.errors

#     assert parsed["user_id"] == user_id
#     assert parsed["order_id"] == order_id
#     assert parsed["limit"] == 5
#     assert parsed["x_token"] == token


# def test_missing_Param(get_order_dep: EndpointSignature[Any]):
#     user_id = "u11b22"
#     token = "token"

#     req_path = dict(user_id=user_id)
#     req_query = dict(limit=b"5")
#     req_header = {"x-token": token}

#     parsed = get_order_dep.prepare_params(
#         req_path=req_path, req_query=req_query, req_header=req_header, body=b""
#     )

#     assert parsed.errors


# def test_user_params_(create_user_dep: EndpointSignature[User]):
#     u = User(1, "2", "user@email.com")
#     body = encode_json(u)

#     parsed = create_user_dep.prepare_params(body=body)
#     assert not parsed.errors
#     assert parsed["user"] == u


# def test_user_params_fail(create_user_dep: EndpointSignature[User]):
#     invalid_user = User(1, 2, 3)  # type: ignore
#     body = encode_json(invalid_user)

#     parsed = create_user_dep.prepare_params(body=body)
#     assert parsed.errors
#     parsed = create_user_dep.prepare_params(body=b"fft")
#     assert parsed.errors
