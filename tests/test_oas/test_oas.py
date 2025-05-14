from typing import Annotated, Union

import pytest
from msgspec import Struct

from lihil import Empty, HTTPException, Payload, Route, Text, status
from lihil.auth.oauth import OAuth2PasswordFlow
from lihil.config import OASConfig
from lihil.interface import is_set
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.oas.doc_ui import get_problem_ui_html
from lihil.oas.schema import (
    detail_base_to_content,
    generate_oas,
    generate_op_from_ep,
    get_ep_security,
    get_path_item_from_route,
    get_resp_schemas,
)
from lihil.plugins.testclient import LocalClient
from lihil.problems import collect_problems
from lihil.routing import EndpointProps


class User(Payload, tag=True):
    name: str
    age: int


class Order(Payload, tag=True):
    id: str
    price: float


@pytest.fixture
def user_route():
    route = Route("/user/{user_id}/order/{order_id}")
    route.setup()
    return route


class OrderNotFound(HTTPException[str]):
    "No Such Order!"


oas_config = OASConfig()


def test_get_order_schema(user_route: Route):
    async def get_order(
        user_id: str | int, order_id: str, q: int | str, l: str, u: User
    ) -> Order | User: ...

    user_route.post(errors=OrderNotFound)(get_order)

    current_ep = user_route.endpoints["POST"]
    user_route.setup()
    ep_rt = current_ep.sig.return_params[200]
    ep_rt.type_ == Union[Order, User]
    components = {"schemas": {}}
    ep_oas = generate_op_from_ep(
        current_ep, components["schemas"], {}, oas_config.problem_path
    )


def test_get_hello_return(user_route: Route):
    @user_route.get
    async def get_hello(
        user_id: str, order_id: str, q: int, l: str, u: User
    ) -> Annotated[Text, status.OK]: ...

    current_ep = user_route.get_endpoint(get_hello)
    user_route.setup()
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


def test_complex_route(complex_route: Route):

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
    complex_route.setup()

    oas = generate_oas([complex_route], oas_config, "0.1.0")
    assert oas


async def test_call_openai():
    lc = LocalClient()
    oas_route = get_openapi_route(oas_config, routes=[], app_version="0.1.0")
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
    route.setup()
    schema = get_resp_schemas(ep, {}, "")
    assert schema["200"].description == "No Content"


MyAlias = Annotated[Annotated[str, "hha"], "aloha"]


async def test_ep_with_annotated_resp():

    route = Route()

    def empty_ep() -> MyAlias: ...

    route.get(empty_ep)

    ep = route.get_endpoint("GET")
    route.setup()
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


def test_ep_with_status_larger_than_300():
    async def create_user() -> (
        Annotated[str, status.NOT_FOUND] | Annotated[int, status.INTERNAL_SERVER_ERROR]
    ): ...

    route = Route()
    route.post(create_user)
    ep = route.get_endpoint(create_user)
    route.setup()

    get_resp_schemas(ep, {}, "")


def test_ep_without_ret():
    async def create_user(): ...

    route = Route()
    route.post(create_user)
    ep = route.get_endpoint(create_user)
    route.setup()

    get_resp_schemas(ep, {}, "")


def test_ep_with_auth():

    async def get_user(token: str): ...

    route = Route()
    route.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_user)

    ep = route.get_endpoint("GET")
    route.setup()

    sc = {}
    get_ep_security(ep, sc)
    assert sc["OAuth2PasswordBearer"]


def test_ep_with_mutliple_ret():
    async def f() -> Annotated[str, status.OK] | Annotated[int | list[int], status.CREATED]: ...

    lc = LocalClient()

    ep = lc.make_endpoint(f)

    get_resp_schemas(ep, {}, "")


def test_ep_with_auth_scheme():
    async def f() -> Annotated[str, status.OK] | Annotated[int | list[int], status.CREATED]: ...

    lc = LocalClient()

    ep = lc.make_endpoint(f)
    get_resp_schemas(ep, {}, "")
