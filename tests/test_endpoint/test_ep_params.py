import sys
from typing import Annotated
from unittest import mock

import msgspec
import pytest
from starlette.requests import Request

from lihil import MISSING, DependentNode, Form, Graph, Param, Payload, Request, use
from lihil.config import lhl_set_config
from lihil.errors import InvalidParamError, InvalidParamSourceError, NotSupportedError
from lihil.plugins.auth.jwt import JWTAuthParam, JWTConfig
from lihil.signature.parser import (
    BodyParam,
    EndpointParser,
    HeaderParam,
    PathParam,
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
# def test_custom_decoder():
#     def decode_int(value: str) -> int:
#         return int(value)

#     decoder = CustomDecoder(decode=decode_int)
#     assert decoder.decode("42") == 42


# Test RequestParamBase and RequestParam
def test_request_Param():
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
    assert param.source == "query"
    assert param.name == param.alias == "test"


# Test PluginParam
# def test_singleton_Param():
#     param = PluginParam(type_=Request, annotation=Request, name="request")
#     assert param.required is True

#     param = PluginParam(type_=EventBus, annotation=EventBus, name="bus", default=None)
#     assert param.required is False


@pytest.fixture
def param_parser() -> EndpointParser:
    return EndpointParser(Graph(), "test")


def test_parsed_params(param_parser: EndpointParser):
    param_parser.graph.analyze(DependentService)

    def str_decoder(x: str) -> str:
        return str(x)

    def dict_decoder(x: bytes):
        return x

    async def endpoint(
        q: Annotated[str, Param(decoder=str_decoder)],
        data: Annotated[dict[str, str], Param("body", decoder=dict_decoder)],
        req: Request,
        service: DependentService,
    ): ...

    sig = param_parser.parse(endpoint)

    q = sig.query_params["q"]
    data = sig.body_param

    assert q.source == "query"
    assert q.type_ == str

    assert data[1].type_ == dict[str, str]

    service = sig.dependencies["service"]
    assert service.dependent == DependentService

    req = sig.plugins["req"]
    assert req.type_ == Request


# Test analyze_param for path parameters
def test_analyze_param_path(param_parser: EndpointParser):
    param_parser.path_keys = ("id",)
    result = param_parser.parse_param("id", int, MISSING)

    assert len(result) == 1
    param = result[0]
    assert param.name == "id"
    assert isinstance(param, PathParam)
    assert param.source == "path"
    assert param.type_ == int


# Test analyze_param for payload
def test_analyze_param_payload(param_parser: EndpointParser):

    result = param_parser.parse_param("data", SamplePayload, MISSING)

    assert len(result) == 1
    param = result[0]
    assert param.name == "data"
    assert isinstance(param, BodyParam)

    assert param.type_ == SamplePayload


def test_analyze_param_union_payload(param_parser: EndpointParser):
    result = param_parser.parse_param("data", SamplePayload | None, MISSING)

    assert len(result) == 1

    param = result[0]
    assert isinstance(param, BodyParam)
    assert param.name == "data"


# Test analyze_param for query parameters
def test_analyze_param_query(param_parser: EndpointParser):
    result = param_parser.parse_param("q", str, MISSING)
    assert len(result) == 1
    param = result[0]
    assert param.name == "q"
    assert isinstance(param, QueryParam)
    assert param.source == "query"


# Test analyze_param for dependencies
def test_analyze_param_dependency(param_parser: EndpointParser):
    graph = Graph()
    graph.node(SimpleDependency)
    param_parser.graph = graph

    result = param_parser.parse_param("dep", SimpleDependency, MISSING)

    assert len(result) == 2
    assert isinstance(result[0], DependentNode)


# Test analyze_param for lihil dependencies
def test_analyze_param_lihil_dep(param_parser: EndpointParser):
    result = param_parser.parse_param("request", Request, MISSING)

    assert len(result) == 1
    param = result[0]
    assert param.name == "request"
    assert isinstance(param, PluginParam)
    assert param.type_ == Request


# Test analyze_markedparam for Query
def test_analyze_markedparam_query(param_parser: EndpointParser):
    result = param_parser.parse_param(
        "page",
        Annotated[int, Param("query")],
        default=MISSING,
    )

    assert len(result) == 1
    p = result[0]
    assert p.name == "page"
    assert isinstance(p, QueryParam)
    assert p.source == "query"


# Test analyze_markedparam for Header
def test_analyze_markedparam_header(param_parser: EndpointParser):
    result = param_parser.parse_param("user_agent", Annotated[str, Param("header")])
    assert len(result) == 1
    p = result[0]
    assert p.name == "user_agent"
    assert isinstance(p, HeaderParam)
    assert p.source == "header"


def test_analyze_markedparam_header_with_alias(param_parser: EndpointParser):
    result = param_parser.parse_param(
        "user_agent", Annotated[str, Param("header", alias="test-alias")]
    )
    assert len(result) == 1
    p = result[0]
    assert p.name == "user_agent"
    assert isinstance(p, HeaderParam)
    assert p.source == "header"
    assert p.alias == "test-alias"


# Test analyze_markedparam for Body
def test_analyze_markedparam_body(param_parser: EndpointParser):
    body_type = Annotated[dict, Param("body")]
    result = param_parser.parse_param("data", body_type)

    assert len(result) == 1
    p = result[0]
    assert p.name == "data"
    assert isinstance(p, BodyParam)


# Test analyze_markedparam for Path
def test_analyze_markedparam_path(param_parser: EndpointParser):
    result = param_parser.parse_param("id", Annotated[int, Param("path")])
    assert len(result) == 1
    assert not isinstance(result[0], DependentNode)
    p = result[0]
    assert p.name == "id"
    assert isinstance(p, PathParam)
    assert p.source == "path"


def test_analyze_multiple_marks(param_parser: EndpointParser):
    with pytest.raises(TypeError):
        param_parser.parse_param("page", Annotated[int, Param("query", "path")])


# Test analyze_markedparam for Use
def test_analyze_markedparam_use(param_parser: EndpointParser):
    param_parser.graph.node(SimpleDependency)

    result = param_parser.parse_param(
        "dep", Annotated[SimpleDependency, use(SimpleDependency)], MISSING
    )

    assert len(result) == 2
    assert isinstance(result[0], DependentNode)


# Test analyze_nodeparams
def test_analyze_nodeparams(param_parser: EndpointParser):
    # Create a node with dependencies

    param_parser.graph.analyze(DependentService)
    result = param_parser.parse_param("service", DependentService)

    # Should return the node itself and its dependencies
    assert isinstance(result[0], DependentNode)


# Test analyze_endpoint_params
def test_analyze_endpoint_params(param_parser: EndpointParser):
    param_parser.path_keys = ("id",)

    def func(id: int, q: str = ""): ...

    sig = param_parser.parse(func)

    # assert isinstance(sig, EndpointParams)
    assert len(sig.path_params) == 1  # Both id and q should be in params
    assert len(sig.query_params) == 1  # Both id and q should be in params

    # Check that path parameter was correctly identified
    assert "id" in sig.path_params


def test_param_parser_parse_unions(param_parser: EndpointParser):
    result = param_parser.parse_param("test", dict[str, int] | list[int])
    assert result
    param = result[0]
    assert param.source == "body"
    assert param.type_ == dict[str, int] | list[int]


def test_param_parser_parse_bytes_union(param_parser: EndpointParser):
    res = param_parser.parse_param("test", bytes)

    param = res[0]
    assert param.source == "query"
    assert param.type_ == bytes

    res = param.decode('{"test": 2}')
    assert isinstance(res, bytes)


def test_invalid_Param(param_parser: EndpointParser):
    with pytest.raises(InvalidParamError):
        param_parser.parse_param("aloha", 5)


def test_textual_field(param_parser: EndpointParser):
    res = param_parser.parse_param("text", bytes)
    assert isinstance(res[0], QueryParam)
    # assert res[0].decoder is to_bytes


def test_form_with_sequence_field(param_parser: EndpointParser):
    class SequenceForm(Payload):
        nums: list[int]

    res = param_parser.parse_param("form", Annotated[SequenceForm, Form()])[0]
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


def test_form_body_with_default_val(param_parser: EndpointParser):
    class LoginInfo(Payload):
        name: str = "name"
        age: int = 15

    class FakeForm:
        def get(self, name):
            return None

    infn = LoginInfo("user", 20)
    param = param_parser.parse_param("data", Annotated[LoginInfo, Form()], infn)[0]
    res = param.decode(FakeForm())
    assert res.name == "name"
    assert res.age == 15


def test_param_repr_with_union_args(param_parser: EndpointParser):
    param = param_parser.parse_param("param", str | int)[0]
    param.__repr__()


def test_body_param_repr(param_parser: EndpointParser):
    with pytest.raises(InvalidParamError):
        param = param_parser.parse_param("data", Annotated[bytes, Form()])[0]

    class UserData(Payload):
        user_name: str
        user_age: int

    param = param_parser.parse_param("data", Annotated[UserData, Form()])[0]


def test_path_param_with_default_fail(param_parser: EndpointParser):
    with pytest.raises(NotSupportedError):
        param_parser.parse_param(
            name="user_id", annotation=Annotated[str, Param("path")], default="user"
        )


def test_multiple_body_is_not_suuported(param_parser: EndpointParser):

    def invalid_ep(
        user_data: Annotated[str, Param("body")],
        order_data: Annotated[str, Param("body")],
    ): ...

    with pytest.raises(NotSupportedError):
        res = param_parser.parse(invalid_ep)


def test_parse_JWTAuth_without_pyjwt_installed(param_parser: EndpointParser):
    with mock.patch.dict("sys.modules", {"jwt": None}):
        if "lihil.plugins.auth.jwt" in sys.modules:
            del sys.modules["lihil.plugins.auth.jwt"]
        del sys.modules["lihil.signature.params"]

    def ep_expects_jwt(user_id: Annotated[str, JWTAuthParam]): ...

    app_config = JWTConfig(JWT_SECRET="test", JWT_ALGORITHMS=["HS256"])
    lhl_set_config(app_config)

    param_parser.parse(ep_expects_jwt)
    lhl_set_config()


def test_JWTAuth_with_custom_decoder(param_parser: EndpointParser):
    from lihil.plugins.auth.jwt import JWTAuthParam

    app_config = JWTConfig(JWT_SECRET="test", JWT_ALGORITHMS=["HS256"])
    lhl_set_config(app_config)

    def ep_expects_jwt(
        user_id: Annotated[str, JWTAuthParam, Param(decoder=lambda c: c)],
    ): ...

    param_parser.parse(ep_expects_jwt)


def decoder1(c: str) -> str: ...
def decoder2(c: str) -> str: ...


ParamP1 = Annotated[str, Param("query", decoder=decoder1)]
ParamP2 = Annotated[ParamP1, Param(decoder=decoder2)]


def test_param_decoder_override(param_parser: EndpointParser):
    r1 = param_parser.parse_param("test", ParamP1)[0]
    assert r1.decoder is decoder1

    r2 = param_parser.parse_param("test", ParamP2)[0]
    assert r2.decoder is decoder2


def test_http_excp_with_typealis():
    from lihil import HTTPException, status

    err = HTTPException(problem_status=status.NOT_FOUND)
    assert err.status == 404


def test_param_with_meta(param_parser: EndpointParser):
    PositiveInt = Annotated[int, msgspec.Meta(gt=0)]
    res = param_parser.parse_param("nums", list[PositiveInt])[0]
    assert res.decode(["1", "2", "3"]) == [1, 2, 3]

    with pytest.raises(msgspec.ValidationError):
        res.decode("[1,2,3,-4]")


def test_param_with_annot_meta(param_parser: EndpointParser):
    UnixName = Annotated[
        str, Param(min_length=1, max_length=32, pattern="^[a-z_][a-z0-9_-]*$")
    ]

    res = param_parser.parse_param("name", UnixName)[0]
    with pytest.raises(msgspec.ValidationError):
        res.decode("5")


def test_constraint_posint(param_parser: EndpointParser):
    PositiveInt = Annotated[int, Param(gt=0)]

    res = param_parser.parse_param("age", PositiveInt)[0]
    with pytest.raises(msgspec.ValidationError):
        res.decode("-5")


from datetime import datetime

TZDATE = Annotated[datetime, Param(tz=True)]


def test_constraint_dt(param_parser: EndpointParser):
    res = param_parser.parse_param("time", TZDATE)[0]

    with pytest.raises(msgspec.ValidationError):
        res.decode("2022-04-02T18:18:10")

    dt = res.decode("2022-04-02T18:18:10-06:00")

    assert isinstance(dt, datetime) and dt.tzinfo


def test_param_with_bytes_in_union(param_parser: EndpointParser):

    with pytest.raises(InvalidParamError):
        res = param_parser.parse_param("n", int | bytes)


def test_parse_cookie(param_parser: EndpointParser):

    t, meta = get_origin_pro(Annotated[str, Param("header", alias="ads_id")])
    assert t == str and meta[0].alias == "ads_id"

    t, meta = get_origin_pro(Annotated[str, Param("cookie", alias="ads_id")])

    res = param_parser.parse_param(
        "cookies", Annotated[str, Param("cookie", alias="ads_id")]
    )[0]
    assert res.cookie_name == "ads_id"

    def cookie_decoder(x):
        x

    res = param_parser.parse_param(
        "cookies",
        Annotated[str, Param("cookie", alias="ads_id", decoder=cookie_decoder)],
    )[0]
    assert res.cookie_name == "ads_id"
    assert res.decoder is cookie_decoder


async def test_endpoint_with_body_decoder(param_parser: EndpointParser):
    class UserData(Payload):
        user_name: str

    def user_decoder(data: bytes) -> UserData: ...
    async def create_user(user: Annotated[UserData, Param(decoder=user_decoder)]): ...

    param_parser.parse(create_user)


async def test_endpoint_with_header_key(param_parser: EndpointParser):

    async def with_header_key(
        user_agen: Annotated[str, Param("header", alias="User-Agent")],
    ): ...
    async def without_header_key(user_agen: Annotated[str, Param("header")]): ...

    param_parser.parse(with_header_key)
    param_parser.parse(without_header_key)


async def test_parse_ep_with_path_key(param_parser: EndpointParser):
    param_parser.path_keys = ("user_id",)

    async def get_user(user_id: str): ...

    sig = param_parser.parse(get_user)
    assert sig.path_params["user_id"]


async def test_endpoint_with_invalid_param(param_parser: EndpointParser):

    with pytest.raises(InvalidParamSourceError):

        async def with_header_key(
            user_agen: Annotated[str, Param("asdf")],
        ): ...


async def test_parse_ep_with_path_key(param_parser: EndpointParser):

    async def get_user(user_id: list[str]): ...

    sig = param_parser.parse(get_user)
    assert sig.query_params["user_id"]
