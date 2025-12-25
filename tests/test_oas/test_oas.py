import pytest
from pytest import importorskip

importorskip("jwt")
importorskip("pydantic")
pytestmark = [pytest.mark.requires_auth, pytest.mark.requires_pydantic]
from typing import Annotated, Union

from msgspec import Struct

from lihil import Empty, HTTPException, Lihil, Param, Payload, Route, Text, status
from lihil.config import OASConfig
from lihil.interface import is_set
from lihil.local_client import LocalClient
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.oas.model import OASResponse
from lihil.oas.doc_ui import get_problem_ui_html
from lihil.oas.schema import (
    SchemaGenerationAggregateError,
    detail_base_to_content,
    generate_oas,
    generate_op_from_ep,
    get_ep_security,
    get_path_item_from_route,
    get_resp_schemas,
    oas_schema,
)
from lihil.plugins.auth.jwt import JWTAuthParam
from lihil.plugins.auth.oauth import OAuth2PasswordFlow
from lihil.problems import collect_problems


class User(Payload, tag=True):
    name: str
    age: int


class Order(Payload, tag=True):
    id: str
    price: float


@pytest.fixture
async def user_route():
    route = Route("/user/{user_id}/order/{order_id}")
    return route


class OrderNotFound(HTTPException[str]):
    "No Such Order!"


oas_config = OASConfig()


async def test_get_order_schema(user_route: Route):
    async def get_order(
        user_id: str | int, order_id: str, q: int | str, l: str, u: User
    ) -> Order | User: ...

    user_route.post(problems=OrderNotFound)(get_order)

    current_ep = user_route.get_endpoint("POST")
    ep_rt = current_ep.sig.return_params[200]
    ep_rt.type_ == Union[Order, User]
    components = {"schemas": {}}
    op, errs = generate_op_from_ep(
        current_ep, components["schemas"], {}, oas_config.PROBLEM_PATH
    )
    assert op is not None
    assert not errs


async def test_get_hello_return(user_route: Route):
    @user_route.get
    async def get_hello(
        user_id: str, order_id: str, q: int, l: str, u: User
    ) -> Annotated[Text, status.OK]: ...

    current_ep = user_route.get_endpoint(get_hello)
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
        "GET", func=get_user, problems=[UserNotFoundError, UserNotHappyError]
    )
    complex_route.setup()

    oas = generate_oas([complex_route], oas_config, "0.1.0")
    assert oas


async def test_call_openai():
    lc = LocalClient()

    oas_route = get_openapi_route([], oas_config, "0.1.0")
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
    schema = get_resp_schemas(ep, {}, "")
    assert schema["200"].description == "No Content"


MyAlias = Annotated[Annotated[str, "hha"], "aloha"]


async def test_ep_with_annotated_resp():

    route = Route()

    def empty_ep() -> MyAlias: ...

    route.get(empty_ep)

    ep = route.get_endpoint("GET")
    schema = get_resp_schemas(ep, {}, "")
    assert schema


async def test_ep_not_include_schema():

    route = Route()

    def empty_ep() -> MyAlias: ...

    route.get(empty_ep, in_schema=False)

    ep = route.get_endpoint("GET")
    schema = get_path_item_from_route(route, {}, {}, "", {})
    assert not is_set(schema.get)


async def test_route_not_include_schema():
    route = Route(in_schema=False)
    res = generate_oas([route], oas_config, "")
    assert not res.paths


class Random(Struct):
    name: str


def test_generate_oas_collects_schema_errors_structure():
    class Unknown:
        pass

    api_route = Route("/api")
    admin_route = api_route.sub("/admin")

    @api_route.get
    async def bad_root_response() -> Unknown:
        return Unknown()

    @api_route.post
    async def ok_root_endpoint(data: str) -> dict[str, int]:
        return {"value": 1}

    @admin_route.get
    async def bad_admin_param(admin_id: Unknown) -> None:
        return None

    @admin_route.post
    async def ok_admin_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    api_route.setup()
    admin_route.setup()

    with pytest.raises(SchemaGenerationAggregateError) as exc_info:
        generate_oas([api_route, admin_route], oas_config, "test")

    agg_error = exc_info.value
    assert len(agg_error.errors) == 2

    message = str(agg_error)
    assert (
        "GET /api bad_root_response -> Response[200, application/json [Unknown]]"
        in message
    )
    assert "GET /api/admin bad_admin_param (admin_id: Query[Unknown])" in message


def test_detail_base_to_content():
    assert detail_base_to_content(Random, {}, {})


def test_object_schema_defaults_to_any():
    output = oas_schema(object)
    assert output.component is None
    assert output.result["type"] == "object"


async def test_ep_with_status_larger_than_300():
    async def create_user() -> (
        Annotated[str, status.NOT_FOUND] | Annotated[int, status.INTERNAL_SERVER_ERROR]
    ): ...

    route = Route()
    route.post(create_user)
    ep = route.get_endpoint(create_user)

    get_resp_schemas(ep, {}, "")


def test_collects_multiple_param_errors_same_endpoint():
    class Unknown:
        pass

    route = Route("/multi")

    @route.get
    async def bad_params(x: Unknown, y: Unknown) -> None:
        return None

    route.setup()

    with pytest.raises(SchemaGenerationAggregateError) as exc_info:
        generate_oas([route], oas_config, "test")

    agg = exc_info.value
    # Ensure two param errors are recorded for the same endpoint
    assert "/multi" in agg.error_map
    assert "GET" in agg.error_map["/multi"]
    errs = agg.error_map["/multi"]["GET"]
    assert len(errs) == 2
    # Message contains grouped param contexts on one line
    msg = str(agg)
    assert "(x: Query[Unknown], y: Query[Unknown])" in msg


def test_route_with_multiple_endpoints_have_errors():
    class Unknown:
        pass

    route = Route("/same")

    @route.get
    async def bad_get(a: Unknown) -> None:
        return None

    @route.post
    async def bad_post() -> Unknown:
        return Unknown()

    route.setup()

    with pytest.raises(SchemaGenerationAggregateError) as exc_info:
        generate_oas([route], oas_config, "test")

    agg = exc_info.value
    assert "/same" in agg.error_map
    methods = agg.error_map["/same"]
    assert "GET" in methods and "POST" in methods
    assert len(methods["GET"]) >= 1
    assert len(methods["POST"]) >= 1


async def test_ep_without_ret():
    async def create_user(): ...

    route = Route()
    route.post(create_user)
    ep = route.get_endpoint(create_user)

    get_resp_schemas(ep, {}, "")


async def test_ep_with_auth():

    async def get_user(token: str): ...

    route = Route()
    route.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_user)

    ep = route.get_endpoint("GET")

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


@pytest.mark.requires_pydantic
async def test_route_with_pydantic_schema():
    from pydantic import BaseModel

    class PydanticBody(BaseModel):
        name: str
        age: str

    class PydanticResp(BaseModel):
        email: str

    lc = LocalClient()

    async def create_user(user: PydanticBody) -> PydanticResp: ...

    ep = await lc.make_endpoint(create_user)

    op, errs = generate_op_from_ep(ep, {}, {}, "problems")
    assert op is not None
    assert not errs


def test_oas_schema_of_msgspec_and_pydantic():
    class MSUser(Struct):
        id: str
        email: str

    result = oas_schema(MSUser)
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


def test_generate_tasg():
    class UserProfileDTO(Payload): ...

    class ProfileService:
        async def list_profiles(self, limit, offset) -> list[UserProfileDTO]: ...

    profiles = Route("profiles", deps=[ProfileService])

    @profiles.get
    async def get_profiles(
        service: ProfileService,
        limit: int = 10,
        offset: int = 0,
    ) -> list[UserProfileDTO]:
        return await service.list_profiles(limit, offset)

    lhl = Lihil(profiles)

    oas = lhl.genereate_oas()

    for path, itm in oas.paths.items():
        if path.endswith("profiles"):
            assert itm.get.tags == ["profiles"]


async def test_optional_query():
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

    op, errs = generate_op_from_ep(ep, {}, {}, "problems")
    assert op.parameters[1].schema_["oneOf"]


async def test_jwt_header():
    lc = LocalClient()

    async def create_user(
        auth: Annotated[bytes, JWTAuthParam],
    ): ...

    ep = await lc.make_endpoint(create_user)

    op, errs = generate_op_from_ep(ep, {}, {}, "problems")
