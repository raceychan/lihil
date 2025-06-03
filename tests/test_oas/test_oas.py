from typing import Annotated, Union

import pytest
from msgspec import Struct

from lihil import Empty, HTTPException, Param, Payload, Route, Text, status
from lihil.config import OASConfig
from lihil.interface import is_set
from lihil.local_client import LocalClient
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.oas.doc_ui import get_problem_ui_html
from lihil.oas.schema import (
    detail_base_to_content,
    generate_oas,
    generate_op_from_ep,
    get_ep_security,
    get_path_item_from_route,
    get_resp_schemas,
    json_schema,
)
from lihil.plugins.auth.oauth import OAuth2PasswordFlow
from lihil.problems import collect_problems
from lihil.routing import EndpointProps


class User(Payload, tag=True):
    name: str
    age: int


class Order(Payload, tag=True):
    id: str
    price: float


@pytest.fixture
async def user_route():
    route = Route("/user/{user_id}/order/{order_id}")
    await route.setup()
    return route


class OrderNotFound(HTTPException[str]):
    "No Such Order!"


oas_config = OASConfig()


async def test_get_order_schema(user_route: Route):
    async def get_order(
        user_id: str | int, order_id: str, q: int | str, l: str, u: User
    ) -> Order | User: ...

    user_route.post(errors=OrderNotFound)(get_order)

    current_ep = user_route.endpoints["POST"]
    await user_route.setup()
    ep_rt = current_ep.sig.return_params[200]
    ep_rt.type_ == Union[Order, User]
    components = {"schemas": {}}
    ep_oas = generate_op_from_ep(
        current_ep, components["schemas"], {}, oas_config.PROBLEM_PATH
    )


async def test_get_hello_return(user_route: Route):
    @user_route.get
    async def get_hello(
        user_id: str, order_id: str, q: int, l: str, u: User
    ) -> Annotated[Text, status.OK]: ...

    current_ep = user_route.get_endpoint(get_hello)
    await user_route.setup()
    ep_rt = current_ep.sig.return_params[200]
    assert ep_rt.type_ == bytes


def test_generate_oas():
    "https://editor.swagger.io/"
    oas = generate_oas([user_route], oas_config, "0.1.0")
    assert oas


def test_generate_problems():
    ui = get_problem_ui_html(title="API Problem Details", problems=collect_problems())
    assert ui


class Unhappiness(Payload):
    scale: int
    is_mad: bool


class UserNotHappyError(HTTPException[Unhappiness]):
    "user is not happy with what you are doing"


@pytest.fixture
def complex_route():
    return Route("user")


async def test_complex_route(complex_route: Route):

    class UserNotFoundError(HTTPException[str]):
        "You can't see me"

        __status__ = 404

    async def get_user(user_id: str | int) -> Annotated[Text, status.OK]:
        if user_id != "5":
            raise UserNotFoundError("You can't see me!")

        return "aloha"

    complex_route.add_endpoint(
        "GET", func=get_user, errors=[UserNotFoundError, UserNotHappyError]
    )
    await complex_route.setup()

    oas = generate_oas([complex_route], oas_config, "0.1.0")
    assert oas


async def test_call_openai():
    lc = LocalClient()
    oas = generate_oas([], oas_config, "0.1.0")

    oas_route = get_openapi_route(oas, oas_config.OAS_PATH)
    ep = oas_route.get_endpoint("GET")

    res = await lc.call_endpoint(ep)
    assert res.status_code == 200


async def test_call_doc_ui():
    lc = LocalClient()
    doc_route = get_doc_route(oas_config)
    ep = doc_route.get_endpoint("GET")

    res = await lc.call_endpoint(ep)
    assert res.status_code == 200


async def test_call_problempage():
    lc = LocalClient()
    problem_route = get_problem_route(oas_config, [])
    ep = problem_route.get_endpoint("GET")

    res = await lc.call_endpoint(ep)
    assert res.status_code == 200


async def test_ep_with_empty_resp():

    route = Route()

    def empty_ep() -> Empty: ...

    route.get(empty_ep)

    ep = route.get_endpoint("GET")
    await route.setup()
    schema = get_resp_schemas(ep, {}, "")
    assert schema["200"].description == "No Content"


MyAlias = Annotated[Annotated[str, "hha"], "aloha"]


async def test_ep_with_annotated_resp():

    route = Route()

    def empty_ep() -> MyAlias: ...

    route.get(empty_ep)

    ep = route.get_endpoint("GET")
    await route.setup()
    schema = get_resp_schemas(ep, {}, "")
    assert schema


async def test_ep_not_include_schema():

    route = Route()

    def empty_ep() -> MyAlias: ...

    route.get(empty_ep, in_schema=False)

    ep = route.get_endpoint("GET")
    schema = get_path_item_from_route(route, {}, {}, "")
    assert not is_set(schema.get)


async def test_route_not_include_schema():
    route = Route(props=EndpointProps(in_schema=False))
    res = generate_oas([route], oas_config, "")
    assert not res.paths


class Random(Struct):
    name: str


def test_detail_base_to_content():
    assert detail_base_to_content(Random, {}, {})


async def test_ep_with_status_larger_than_300():
    async def create_user() -> (
        Annotated[str, status.NOT_FOUND] | Annotated[int, status.INTERNAL_SERVER_ERROR]
    ): ...

    route = Route()
    route.post(create_user)
    ep = route.get_endpoint(create_user)
    await route.setup()

    get_resp_schemas(ep, {}, "")


async def test_ep_without_ret():
    async def create_user(): ...

    route = Route()
    route.post(create_user)
    ep = route.get_endpoint(create_user)
    await route.setup()

    get_resp_schemas(ep, {}, "")


async def test_ep_with_auth():

    async def get_user(token: str): ...

    route = Route()
    route.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_user)

    ep = route.get_endpoint("GET")
    await route.setup()

    sc = {}
    get_ep_security(ep, sc)
    assert sc["OAuth2PasswordBearer"]


async def test_ep_with_mutliple_ret():
    async def f() -> (
        Annotated[str, status.OK] | Annotated[int | list[int], status.CREATED]
    ): ...

    lc = LocalClient()

    ep = await lc.make_endpoint(f)

    get_resp_schemas(ep, {}, "")


async def test_ep_with_auth_scheme():
    async def f() -> (
        Annotated[str, status.OK] | Annotated[int | list[int], status.CREATED]
    ): ...

    lc = LocalClient()

    ep = await lc.make_endpoint(f)
    get_resp_schemas(ep, {}, "")


from pydantic import BaseModel


class PydanticBody(BaseModel):
    name: str
    age: str


class PydanticResp(BaseModel):
    email: str


async def test_route_with_pydantic_schema():

    async def create_user(user: PydanticBody) -> PydanticResp: ...

    lc = LocalClient()
    ep = await lc.make_endpoint(create_user)

    result = generate_op_from_ep(ep, {}, {}, "problems")
    assert result


def test_json_schema_of_msgspec_and_pydantic():
    from lihil.plugins.auth.supabase import auth_types

    result = json_schema(auth_types.User)
    assert result


async def test_single_value_param_not_required():
    "before 0.2.14 we set in lihil.oas.schema._single_field_schema that param required is always true"

    lc = LocalClient()

    async def create_user(
        age: int,
        user_id: str | None = None,
        address: Annotated[str, Param("header", alias="address")] = "",
    ): ...

    ep = await lc.make_endpoint(create_user)

    assert not ep.sig.query_params["user_id"].required
    assert ep.sig.query_params["age"].required
    assert not ep.sig.header_params["address"].required
