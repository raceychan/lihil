import sys
from typing import Annotated, Any, Literal
from unittest import mock

import msgspec
import pytest
from starlette.requests import Request

from lihil import (
    MISSING,
    Body,
    DependentNode,
    EventBus,
    Form,
    Graph,
    Header,
    Path,
    Payload,
    Query,
    Request,
    Resolver,
    Use,
)
from lihil.config import AppConfig, SecurityConfig
from lihil.errors import InvalidMarkTypeError, NotSupportedError
from lihil.interface.marks import HEADER_REQUEST_MARK, Cookie, param_mark
from lihil.plugins.registry import register_plugin_provider, remove_plugin_provider
from lihil.signature.params import (
    BodyParam,
    CustomDecoder,
    EndpointParams,
    HeaderParam,
    ParamParser,
    PathParam,
    PluginBase,
    PluginParam,
    QueryParam,
)
from lihil.utils.typing import get_origin_pro


# Helper classes for testing
class SamplePayload(Payload):
    name: str
    age: int


class SimpleDependency:
    def __init__(self, value: str):
        self.value = value


class DependentService:
    def __init__(self, dep: SimpleDependency):
        self.dep = dep


# Test CustomDecoder
def test_custom_decoder():
    def decode_int(value: str) -> int:
        return int(value)

    decoder = CustomDecoder(decode=decode_int)
    assert decoder.decode("42") == 42


# Test RequestParamBase and RequestParam
def test_request_param():
    # Test with default value
    param = QueryParam(
        type_=str,
        annotation=str,
        name="test",
        alias="test",
        decoder=lambda x: str(x),
        default="default",
    )
    assert param.required is False

    # Test without default value
    param = QueryParam(
        type_=int,
        annotation=str,
        name="test",
        alias="test",
        decoder=lambda x: int(x),
    )
    assert param.required is True

    # Test decode method
    assert param.decode("42") == 42

    # Test repr
    assert repr(param)
    assert param.location == "query"
    assert param.name == param.alias == "test"


# Test PluginParam
def test_singleton_param():
    param = PluginParam(type_=Request, annotation=Request, name="request")
    assert param.required is True

    param = PluginParam(type_=EventBus, annotation=EventBus, name="bus", default=None)
    assert param.required is False


@pytest.fixture
def param_parser() -> ParamParser:
    return ParamParser(Graph())


def test_parsed_params(param_parser: ParamParser):
    param_parser.graph.analyze(DependentService)

    def str_decoder(x: str) -> str:
        return str(x)

    def dict_decoder(x: bytes):
        return x

    async def endpoint(
        q: Annotated[str, CustomDecoder(str_decoder)],
        data: Annotated[Body[dict[str, str]], CustomDecoder(dict_decoder)],
        req: Request,
        service: DependentService,
    ): ...

    res = param_parser.parse(endpoint)

    q = res.params["q"]
    data = res.bodies["data"]

    assert q.location == "query"
    assert q.type_ == str

    assert data.type_ == dict[str, str]

    service = res.nodes["service"]
    assert service.dependent == DependentService

    req = res.plugins["req"]
    assert req.type_ == Request


# Test analyze_param for path parameters
def test_analyze_param_path(param_parser: ParamParser):
    param_parser.path_keys = ("id",)
    result = param_parser.parse_param("id", int, MISSING)

    assert len(result) == 1
    param = result[0]
    assert param.name == "id"
    assert isinstance(param, PathParam)
    assert param.location == "path"
    assert param.type_ == int


# Test analyze_param for payload
def test_analyze_param_payload(param_parser):

    result = param_parser.parse_param("data", SamplePayload, MISSING)

    assert len(result) == 1
    param = result[0]
    assert param.name == "data"
    assert isinstance(param, BodyParam)

    assert param.type_ == SamplePayload


def test_analyze_param_union_payload(param_parser: ParamParser):
    result = param_parser.parse_param("data", Body[SamplePayload | None], MISSING)

    assert len(result) == 1

    if isinstance(result[0], DependentNode):
        raise Exception

    param = result[0]
    assert param.name == "data"
    assert isinstance(param, BodyParam)


# Test analyze_param for query parameters
def test_analyze_param_query(param_parser: ParamParser):
    result = param_parser.parse_param("q", str, MISSING)
    assert len(result) == 1
    param = result[0]
    assert param.name == "q"
    assert isinstance(param, QueryParam)
    assert param.location == "query"


# Test analyze_param for dependencies
def test_analyze_param_dependency(param_parser: ParamParser):
    graph = Graph()
    graph.node(SimpleDependency)
    param_parser.graph = graph

    result = param_parser.parse_param("dep", SimpleDependency, MISSING)

    assert len(result) == 2
    assert isinstance(result[0], DependentNode)


# Test analyze_param for lihil dependencies
def test_analyze_param_lihil_dep(param_parser: ParamParser):
    result = param_parser.parse_param("request", Request, MISSING)

    assert len(result) == 1
    param = result[0]
    assert param.name == "request"
    assert isinstance(param, PluginParam)
    assert param.type_ == Request


# Test analyze_markedparam for Query
def test_analyze_markedparam_query(param_parser: ParamParser):
    query_type = Query[int]
    result = param_parser.parse_param(
        "page",
        query_type,
        default=MISSING,
    )

    assert len(result) == 1
    param = result[0]
    assert param.name == "page"
    assert isinstance(param, QueryParam)
    assert param.location == "query"


# Test analyze_markedparam for Header
def test_analyze_markedparam_header(param_parser: ParamParser):
    result = param_parser.parse_param("user_agent", Header[str])
    assert len(result) == 1
    param = result[0]
    assert param.name == "user_agent"
    assert isinstance(param, HeaderParam)
    assert param.location == "header"


def test_analyze_markedparam_header_with_alias(param_parser: ParamParser):
    result = param_parser.parse_param("user_agent", Header[str, "test-alias"])
    assert len(result) == 1
    param = result[0]
    assert param.name == "user_agent"
    assert isinstance(param, HeaderParam)
    assert param.location == "header"
    assert param.alias == "test-alias"


# Test analyze_markedparam for Body
def test_analyze_markedparam_body(param_parser: ParamParser):
    body_type = Body[dict]
    result = param_parser.parse_param("data", body_type)

    assert len(result) == 1
    param = result[0]
    assert param.name == "data"
    assert isinstance(param, BodyParam)


# Test analyze_markedparam for Path
def test_analyze_markedparam_path(param_parser: ParamParser):
    path_type = Path[int]
    result = param_parser.parse_param("id", path_type)
    assert len(result) == 1
    assert not isinstance(result[0], DependentNode)
    param = result[0]
    assert param.name == "id"
    assert isinstance(param, PathParam)
    assert param.location == "path"


def test_analyze_multiple_marks(param_parser: ParamParser):
    with pytest.raises(NotSupportedError):
        param_parser.parse_param("page", Query[int] | Path[int])


# Test analyze_markedparam for Use
def test_analyze_markedparam_use(param_parser: ParamParser):
    param_parser.graph.node(SimpleDependency)

    use_type = Use[SimpleDependency]
    result = param_parser.parse_param("dep", use_type, MISSING)

    assert len(result) == 2
    assert isinstance(result[0], DependentNode)


# Test analyze_nodeparams
def test_analyze_nodeparams(param_parser: ParamParser):
    # Create a node with dependencies

    param_parser.graph.analyze(DependentService)
    result = param_parser.parse_param("service", DependentService)

    # Should return the node itself and its dependencies
    assert isinstance(result[0], DependentNode)


# Test analyze_endpoint_params
def test_analyze_endpoint_params(param_parser: ParamParser):
    param_parser.path_keys = ("id",)

    def func(id: int, q: str = ""): ...

    result = param_parser.parse(func)

    assert isinstance(result, EndpointParams)
    assert len(result.params) == 2  # Both id and q should be in params

    # Check that path parameter was correctly identified
    path_params = result.get_location("path")
    assert len(path_params) == 1
    assert "id" in path_params


def test_param_parser_parse_unions(param_parser: ParamParser):
    with pytest.raises(NotSupportedError):
        param_parser.parse_param("test", dict[str, int] | list[int])


def test_param_parser_parse_bytes_union(param_parser: ParamParser):
    res = param_parser.parse_param("test", bytes)

    param = res[0]
    assert param.location == "query"
    assert param.type_ == bytes

    res = param.decode('{"test": 2}')
    assert isinstance(res, bytes)


def test_invalid_param(param_parser: ParamParser):
    with pytest.raises(NotSupportedError):
        param_parser.parse_param("aloha", 5)


def test_textual_field(param_parser: ParamParser):
    res = param_parser.parse_param("text", bytes)
    assert isinstance(res[0], QueryParam)
    # assert res[0].decoder is to_bytes


def test_form_with_sequence_field(param_parser: ParamParser):
    class SequenceForm(Payload):
        nums: list[int]

    res = param_parser.parse_param("form", Form[SequenceForm])[0]
    assert isinstance(res, BodyParam)
    assert res.type_ is SequenceForm

    class FakeForm:
        def __init__(self, content):
            self.content = content

        def getlist(self, name: str):
            return self.content[name]

    decoder = res.decoder

    res = decoder(FakeForm(dict(nums=[1, 2, 3])))
    assert res == SequenceForm([1, 2, 3])


def test_form_body_with_default_val(param_parser: ParamParser):
    class LoginInfo(Payload):
        name: str = "name"
        age: int = 15

    class FakeForm:
        def get(self, name):
            return None

    infn = LoginInfo("user", 20)
    param = param_parser.parse_param("data", Form[LoginInfo], infn)[0]
    res = param.decode(FakeForm())
    assert res.name == "name"
    assert res.age == 15


def test_param_repr_with_union_args(param_parser: ParamParser):
    param = param_parser.parse_param("param", str | int)[0]
    param.__repr__()


def test_body_param_repr(param_parser: ParamParser):
    param = param_parser.parse_param("data", Form[bytes])[0]
    param.__repr__()


type Cached[T] = Annotated[T, param_mark("cached")]


class CachedProvider(PluginBase):
    async def process(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ) -> None:
        params["param"] = "cached"

    def parse(self, name: str, type_: type, default, annotation):
        return PluginParam(
            type_=type_,
            name=name,
            annotation=annotation,
            default=default,
            processor=self.process,
        )


def test_param_provider(param_parser: ParamParser):
    provider = CachedProvider()
    register_plugin_provider(Cached[str], provider)

    param = param_parser.parse_param("data", Cached[str])[0]
    assert isinstance(param, PluginParam)
    assert param.type_ == str

    with pytest.raises(Exception) as exc:
        register_plugin_provider("cached", provider)

    remove_plugin_provider(Cached[str])


def test_param_provider_with_invalid_mark(param_parser):
    with pytest.raises(InvalidMarkTypeError):
        register_plugin_provider(5, None)

    with pytest.raises(InvalidMarkTypeError):
        register_plugin_provider(Annotated[str, "asdf"], None)


def test_param_provider_with_invalid_plugin(param_parser: ParamParser):
    assert not param_parser.is_lhl_primitive(5)


def test_path_param_with_default_fail(param_parser: ParamParser):
    with pytest.raises(NotSupportedError):
        param_parser.parse_param(name="user_id", annotation=Path[str], default="user")


def test_multiple_body_is_not_suuported(param_parser: ParamParser):

    def invalid_ep(user_data: Body[str], order_data: Body[str]): ...

    res = param_parser.parse(invalid_ep)

    with pytest.raises(NotSupportedError):
        res.get_body()


def test_parse_JWTAuth_without_pyjwt_installed(param_parser: ParamParser):
    with mock.patch.dict("sys.modules", {"jwt": None}):
        if "lihil.auth.jwt" in sys.modules:
            del sys.modules["lihil.auth.jwt"]
        del sys.modules["lihil.signature.params"]

    from lihil.auth.jwt import JWTAuth

    def ep_expects_jwt(user_id: JWTAuth[str]): ...

    param_parser.app_config = AppConfig(
        security=SecurityConfig(jwt_secret="test", jwt_algorithms=["HS256"])
    )

    param_parser.parse(ep_expects_jwt)


def test_JWTAuth_with_custom_decoder(param_parser: ParamParser):
    from lihil.auth.jwt import JWTAuth
    from lihil.interface import CustomDecoder

    def ep_expects_jwt(
        user_id: Annotated[JWTAuth[str], CustomDecoder(lambda c: c)],
    ): ...

    param_parser.parse(ep_expects_jwt)


def test_custom_plugin(param_parser: ParamParser):
    from lihil.plugins.registry import PluginBase

    class MyPlugin(PluginBase): ...

    def ep_expects_jwt(user_id: Annotated[str, MyPlugin()]): ...

    param_parser.parse(ep_expects_jwt)


def decoder1(c: str) -> str: ...
def decoder2(c: str) -> str: ...


type ParamP1 = Annotated[Query[str], CustomDecoder(decoder1)]
type ParamP2 = Annotated[ParamP1, CustomDecoder(decoder2)]


def test_param_decoder_override(param_parser: ParamParser):
    r1 = param_parser.parse_param("test", ParamP1)[0]
    assert r1.decoder is decoder1

    r2 = param_parser.parse_param("test", ParamP2)[0]
    assert r2.decoder is decoder2


def test_http_excp_with_typealis():
    from lihil import HTTPException, status

    err = HTTPException(problem_status=status.NOT_FOUND)
    assert err.status == 404


def test_param_with_meta(param_parser: ParamParser):
    PositiveInt = Annotated[int, msgspec.Meta(gt=0)]
    res = param_parser.parse_param("nums", list[PositiveInt])[0]
    assert res.decode(["1", "2", "3"]) == [1, 2, 3]

    with pytest.raises(msgspec.ValidationError):
        res.decode("[1,2,3,-4]")


def test_param_with_annot_meta(param_parser: ParamParser):
    UnixName = Annotated[
        str, msgspec.Meta(min_length=1, max_length=32, pattern="^[a-z_][a-z0-9_-]*$")
    ]

    res = param_parser.parse_param("name", UnixName)[0]
    with pytest.raises(msgspec.ValidationError):
        res.decode("5")


def test_constraint_posint(param_parser: ParamParser):
    PositiveInt = Annotated[int, msgspec.Meta(gt=0)]

    res = param_parser.parse_param("age", PositiveInt)[0]
    with pytest.raises(msgspec.ValidationError):
        res.decode("-5")


from datetime import datetime

type TZDATE = Annotated[datetime, msgspec.Meta(tz=True)]


def test_constraint_dt(param_parser: ParamParser):
    res = param_parser.parse_param("time", TZDATE)[0]

    with pytest.raises(msgspec.ValidationError):
        res.decode("2022-04-02T18:18:10")

    dt = res.decode("2022-04-02T18:18:10-06:00")

    assert isinstance(dt, datetime) and dt.tzinfo


def test_param_with_bytes_in_union(param_parser: ParamParser):

    with pytest.raises(NotSupportedError):
        res = param_parser.parse_param("n", int | bytes)


def test_parse_cookie(param_parser: ParamParser):

    t, meta = get_origin_pro(Header[str, "ads_id"])
    assert t == str and meta == ["ads_id", HEADER_REQUEST_MARK]

    t, meta = get_origin_pro(Cookie[str, Literal["ads_id"]])

    res = param_parser.parse_param("cookies", Cookie[str, "ads_id"])[0]
    assert res.cookie_name == "ads_id"

    def cookie_decoder(x):
        x

    res = param_parser.parse_param(
        "cookies", Annotated[Cookie[str, "ads_id"], CustomDecoder(cookie_decoder)]
    )[0]
    assert res.cookie_name == "ads_id"
    assert res.decoder is cookie_decoder


async def test_endpoint_with_body_decoder(param_parser: ParamParser):
    class UserData(Payload):
        user_name: str

    def user_decoder(data: bytes) -> UserData: ...
    async def create_user(user: Annotated[UserData, CustomDecoder(user_decoder)]): ...


    param_parser.parse(create_user)


async def test_endpoint_with_header_key(param_parser: ParamParser):

    async def with_header_key(user_agen: Header[str, Literal["User-Agent"]]): ...
    async def without_header_key(user_agen: Header[str]): ...


    param_parser.parse(with_header_key)
    param_parser.parse(without_header_key)


async def test_parse_ep_with_path_key(param_parser: ParamParser):

    async def get_user(user_id: str): ...

    res = param_parser.parse(get_user, ("user_id",))
    assert res.params["user_id"].location == "path"
