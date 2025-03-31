from inspect import Parameter, signature
from typing import Annotated, Union

import pytest

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
from lihil.di.params import (
    CustomDecoder,
    EndpointParams,
    ParamParser,
    PluginParam,
    RequestBodyParam,
    RequestParam,
    to_bytes,
)
from lihil.errors import NotSupportedError
from lihil.interface.marks import param_mark


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
    param = RequestParam(
        type_=str,
        annotation=str,
        name="test",
        alias="test",
        decoder=lambda x: str(x),
        location="query",
        default="default",
    )
    assert param.required is False

    # Test without default value
    param = RequestParam(
        type_=int,
        annotation=str,
        name="test",
        alias="test",
        decoder=lambda x: int(x),
        location="query",
    )
    assert param.required is True

    # Test decode method
    assert param.decode("42") == 42

    # Test repr
    assert "RequestParam<query>(test: int)" in repr(param)


# Test PluginParam
def test_singleton_param():
    param = PluginParam(type_=Request, name="request")
    assert param.required is True

    param = PluginParam(type_=EventBus, name="bus", default=None)
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

    func_params = tuple(signature(endpoint).parameters.items())

    res = param_parser.parse(func_params)

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
    assert isinstance(param, RequestParam)
    assert param.location == "path"
    assert param.type_ == int


# Test analyze_param for payload
def test_analyze_param_payload(param_parser):

    result = param_parser.parse_param("data", SamplePayload, MISSING)

    assert len(result) == 1
    param = result[0]
    assert param.name == "data"
    assert isinstance(param, RequestBodyParam)

    assert param.type_ == SamplePayload


def test_analyze_param_union_payload(param_parser: ParamParser):
    result = param_parser.parse_param("data", Body[SamplePayload | None], MISSING)

    assert len(result) == 1

    if isinstance(result[0], DependentNode):
        raise Exception

    param = result[0]
    assert param.name == "data"
    assert isinstance(param, RequestBodyParam)


# Test analyze_param for query parameters
def test_analyze_param_query(param_parser: ParamParser):
    result = param_parser.parse_param("q", str, MISSING)
    assert len(result) == 1
    param = result[0]
    assert param.name == "q"
    assert isinstance(param, RequestParam)
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
    assert isinstance(param, RequestParam)
    assert param.location == "query"


# Test analyze_markedparam for Header
def test_analyze_markedparam_header(param_parser: ParamParser):
    result = param_parser.parse_param("user_agent", Header[str])
    assert len(result) == 1
    param = result[0]
    assert param.name == "user_agent"
    assert isinstance(param, RequestParam)
    assert param.location == "header"


def test_analyze_markedparam_header_with_alias(param_parser: ParamParser):
    result = param_parser.parse_param("user_agent", Header[str, "test-alias"])
    assert len(result) == 1
    param = result[0]
    assert param.name == "user_agent"
    assert isinstance(param, RequestParam)
    assert param.location == "header"
    assert param.alias == "test-alias"


# Test analyze_markedparam for Body
def test_analyze_markedparam_body(param_parser: ParamParser):
    body_type = Body[dict]
    result = param_parser.parse_param("data", body_type)

    assert len(result) == 1
    param = result[0]
    assert param.name == "data"
    assert isinstance(param, RequestBodyParam)


# Test analyze_markedparam for Path
def test_analyze_markedparam_path(param_parser: ParamParser):
    path_type = Path[int]
    result = param_parser.parse_param("id", path_type)
    assert len(result) == 1
    assert not isinstance(result[0], DependentNode)
    param = result[0]
    assert param.name == "id"
    assert isinstance(param, RequestParam)
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

    # Create function parameters
    param1 = Parameter("id", Parameter.POSITIONAL_OR_KEYWORD, annotation=int)
    param2 = Parameter("q", Parameter.POSITIONAL_OR_KEYWORD, annotation=str, default="")

    func_params = [("id", param1), ("q", param2)]

    result = param_parser.parse(func_params)

    assert isinstance(result, EndpointParams)
    assert len(result.params) == 2  # Both id and q should be in params

    # Check that path parameter was correctly identified
    path_params = result.get_location("path")
    assert len(path_params) == 1
    assert "id" in path_params


def test_param_parser_parse_unions(param_parser: ParamParser):
    res = param_parser.parse_param("test", dict[str, int] | list[int])

    param = res[0]
    assert param.location == "query"
    assert param.type_ == Union[dict[str, int], list[int]]

    res = param.decode('{"test": 2}')
    assert isinstance(res, dict)


def test_param_parser_parse_bytes_union(param_parser: ParamParser):
    res = param_parser.parse_param("test", list[int] | bytes)

    param = res[0]
    assert param.location == "query"
    assert param.type_ == Union[list[int], bytes]

    res = param.decode('{"test": 2}')
    assert isinstance(res, bytes)


def test_invalid_param(param_parser: ParamParser):
    with pytest.raises(NotSupportedError):
        param_parser.parse_param("aloha", 5)


def test_textual_field(param_parser: ParamParser):
    res = param_parser.parse_param("text", bytes)
    assert isinstance(res[0], RequestParam)
    assert res[0].decoder is to_bytes


def test_form_with_sequence_field(param_parser: ParamParser):
    class SequenceForm(Payload):
        nums: list[int]

    res = param_parser.parse_param("form", Form[SequenceForm])[0]
    assert isinstance(res, RequestBodyParam)
    assert res.type_ is SequenceForm

    class FakeForm:
        def __init__(self, content):
            self.content = content

        def getlist(self, name: str):
            return self.content[name]

    decoder = res.decoder

    res = decoder(FakeForm(dict(nums=[1, 2, 3])))
    assert res == SequenceForm([1, 2, 3])


@pytest.mark.skip("do this later")
def test_form_with_default_val(param_parser: ParamParser): ...


def test_param_repr_with_union_args(param_parser: ParamParser):
    param = param_parser.parse_param("param", str | int)[0]
    param.__repr__()


def test_body_param_repr(param_parser: ParamParser):
    param = param_parser.parse_param("data", Form[bytes])[0]
    param.__repr__()


type Cached[T] = Annotated[T, param_mark("cached")]


class CachedProvider:
    def load(self, request: Request, resolver: Resolver) -> str:
        return "cached"

    def parse(self, name: str, type_: type, default, annotation, param_meta):
        return PluginParam(type_=type_, name=name, loader=self.load)


def test_param_provider(param_parser: ParamParser):
    provider = CachedProvider()
    param_parser.register_provider(Cached[str], provider)

    param = param_parser.parse_param("data", Cached[str])[0]
    assert isinstance(param, PluginParam)
    assert param.type_ == str
