from inspect import Parameter
from typing import Annotated, Union

import pytest
from ididi import DependentNode, Graph
from starlette.requests import Request

from lihil.plugins.bus import EventBus
from lihil.di.params import (
    CustomDecoder,
    ParsedParams,
    RequestParam,
    SingletonParam,
    analyze_markedparam,
    analyze_nodeparams,
    analyze_param,
    analyze_request_params,
    textdecoder_factory,
)
from lihil.interface import MISSING, Payload
from lihil.interface.marks import Body, Header, Path, Query, Use


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
        name="test",
        alias="test",
        decoder=lambda x: str(x),
        location="query",
        default="default",
    )
    assert param.required is False

    # Test without default value
    param = RequestParam(
        type_=int, name="test", alias="test", decoder=lambda x: int(x), location="query"
    )
    assert param.required is True

    # Test decode method
    assert param.decode("42") == 42

    # Test repr
    assert "RequestParam<query>(test: int)" in repr(param)


# Test SingletonParam
def test_singleton_param():
    param = SingletonParam(type_=Request, name="request")
    assert param.required is True

    param = SingletonParam(type_=EventBus, name="bus", default=None)
    assert param.required is False


def test_parsed_params():
    graph = Graph()
    params = ParsedParams()

    # Create test parameters
    query_param = RequestParam(
        type_=str, name="q", alias="q", decoder=lambda x: str(x), location="query"
    )

    body_param = RequestParam(
        type_=dict, name="data", alias="data", decoder=lambda x: dict(), location="body"
    )

    singleton_param = SingletonParam(type_=Request, name="request")

    # Create a mock DependentNode
    node = graph.analyze(DependentService)

    # Test collect_param
    params.collect_param("q", [("q", query_param)])
    params.collect_param("data", [("data", body_param)])
    params.collect_param("request", [("request", singleton_param)])
    params.collect_param("service", [node])

    # Test get_location
    query_params = params.get_location("query")
    assert len(query_params) == 1
    assert query_params[0][0] == "q"

    # Test get_body
    body = params.get_body()
    assert body is not None
    assert body[0] == "data"

    # Test multiple bodies (should raise NotImplementedError)
    another_body = RequestParam(
        type_=dict,
        name="another",
        alias="another",
        decoder=lambda x: dict(),
        location="body",
    )
    params.collect_param("another", [("another", another_body)])

    with pytest.raises(NotImplementedError):
        params.get_body()


# Test analyze_param for path parameters
def test_analyze_param_path():
    graph = Graph()
    seen = set()
    path_keys = ("id",)

    result = analyze_param(graph, "id", seen, path_keys, int, MISSING)

    assert len(result) == 1
    name, param = result[0]
    assert name == "id"
    assert isinstance(param, RequestParam)
    assert param.location == "path"
    assert param.type_ == int


# Test analyze_param for payload
def test_analyze_param_payload():
    graph = Graph()
    seen = set()
    path_keys = ()

    result = analyze_param(graph, "data", seen, path_keys, SamplePayload, MISSING)

    assert len(result) == 1
    name, param = result[0]
    assert name == "data"
    assert isinstance(param, RequestParam)
    assert param.location == "body"
    assert param.type_ == SamplePayload


# Test analyze_param for union type with payload
def test_analyze_param_union_payload():
    graph = Graph()
    seen: set[str] = set()
    path_keys = ()

    result = analyze_param(
        graph, "data", seen, path_keys, Body[SamplePayload | None], MISSING
    )

    assert len(result) == 1

    if isinstance(result[0], DependentNode):
        raise Exception

    name, param = result[0]
    assert name == "data"
    assert isinstance(param, RequestParam)
    assert param.location == "body"


# Test analyze_param for query parameters
def test_analyze_param_query():
    graph = Graph()
    seen = set()
    path_keys = ()

    result = analyze_param(graph, "q", seen, path_keys, str, MISSING)

    assert len(result) == 1
    name, param = result[0]
    assert name == "q"
    assert isinstance(param, RequestParam)
    assert param.location == "query"


# Test analyze_param for dependencies
def test_analyze_param_dependency():
    graph = Graph()
    graph.node(SimpleDependency)
    seen = set()
    path_keys = ()

    result = analyze_param(graph, "dep", seen, path_keys, SimpleDependency, MISSING)

    assert len(result) == 2
    assert isinstance(result[0], DependentNode)


# Test analyze_param for lihil dependencies
def test_analyze_param_lihil_dep():
    graph = Graph()
    seen = set()
    path_keys = ()

    result = analyze_param(graph, "request", seen, path_keys, Request, MISSING)

    assert len(result) == 1
    name, param = result[0]
    assert name == "request"
    assert isinstance(param, SingletonParam)
    assert param.type_ == Request


# Test analyze_markedparam for Query
def test_analyze_markedparam_query():
    graph = Graph()
    seen = set()
    path_keys = ()

    query_type = Query[int]
    result = analyze_markedparam(
        graph, "page", seen, path_keys, query_type, Annotated, MISSING
    )

    assert len(result) == 1
    name, param = result[0]
    assert name == "page"
    assert isinstance(param, RequestParam)
    assert param.location == "query"


# Test analyze_markedparam for Header
def test_analyze_markedparam_header():
    graph = Graph()
    seen = set()
    path_keys = ()

    result = analyze_markedparam(
        graph, "user_agent", seen, path_keys, Header[str], Header
    )
    assert len(result) == 1
    name, param = result[0]
    assert name == "user_agent"
    assert isinstance(param, RequestParam)
    assert param.location == "header"


# Test analyze_markedparam for Body
def test_analyze_markedparam_body():
    graph = Graph()
    seen = set()
    path_keys = ()

    body_type = Body[dict]
    result = analyze_markedparam(graph, "data", seen, path_keys, body_type)

    assert len(result) == 1
    name, param = result[0]
    assert name == "data"
    assert isinstance(param, RequestParam)
    assert param.location == "body"


# Test analyze_markedparam for Path
def test_analyze_markedparam_path():
    graph = Graph()
    seen = set()
    path_keys = ()

    path_type = Path[int]
    result = analyze_markedparam(graph, "id", seen, path_keys, path_type)

    assert len(result) == 1
    assert not isinstance(result[0], DependentNode)
    name, param = result[0]
    assert name == "id"
    assert isinstance(param, RequestParam)
    assert param.location == "path"


# Test analyze_markedparam for Use
def test_analyze_markedparam_use():
    graph = Graph()
    graph.node(SimpleDependency)
    seen = set()
    path_keys = ()

    use_type = Use[SimpleDependency]
    result = analyze_param(
        graph,
        "dep",
        seen,
        path_keys,
        use_type,
        MISSING,
    )

    assert len(result) == 2
    assert isinstance(result[0], DependentNode)


# Test analyze_nodeparams
def test_analyze_nodeparams():
    graph = Graph()
    graph.node(SimpleDependency)
    seen: set[str] = set()
    path_keys: tuple[str, ...] = ()

    # Create a node with dependencies
    node = graph.analyze(DependentService)

    result = analyze_nodeparams(node, graph, seen, path_keys)

    # Should return the node itself and its dependencies
    assert len(result) >= 1
    assert result[0] == node


# Test analyze_request_params
def test_analyze_request_params():
    graph = Graph()
    seen = set(["id"])
    path_keys = ("id",)

    # Create function parameters
    param1 = Parameter("id", Parameter.POSITIONAL_OR_KEYWORD, annotation=int)
    param2 = Parameter("q", Parameter.POSITIONAL_OR_KEYWORD, annotation=str, default="")

    func_params = [("id", param1), ("q", param2)]

    result = analyze_request_params(func_params, graph, seen, path_keys)

    assert isinstance(result, ParsedParams)
    assert len(result.params) == 2  # Both id and q should be in params

    # Check that path parameter was correctly identified
    path_params = result.get_location("path")
    assert len(path_params) == 1
    assert path_params[0][0] == "id"


# ... existing code ...


def test_analyze_markedparam_with_custom_decoder():
    graph = Graph()
    seen = set()
    path_keys = ()

    def custom_decode(value: str) -> int:
        return int(value)

    query_type = Annotated[Query[int], CustomDecoder(custom_decode)]

    result = analyze_markedparam(graph, "page", seen, path_keys, query_type)

    assert len(result) == 1
    name, param = result[0]
    assert name == "page"
    assert isinstance(param, RequestParam)
    assert param.location == "query"
    assert param.decoder is custom_decode


def test_analyze_markedparam_with_factory():
    from ididi import use

    graph = Graph()
    seen = set()
    path_keys = ()

    def factory() -> SimpleDependency:
        return SimpleDependency("test")

    config = {"reuse": False}
    annotated_type = Annotated[SimpleDependency, use(factory, **config)]

    result = analyze_markedparam(
        graph, "dep", seen, path_keys, annotated_type, Annotated, MISSING
    )

    assert len(result) >= 1
    assert isinstance(result[0], DependentNode)


def test_analyze_markedparam_with_nested_origin():
    graph = Graph()
    seen = set()
    path_keys = ()

    # Create a nested annotated type
    inner_type = Query[int]
    outer_type = Annotated[inner_type, "metadata"]

    result = analyze_markedparam(graph, "page", seen, path_keys, outer_type)

    assert len(result) == 1
    name, param = result[0]
    assert name == "page"
    assert isinstance(param, RequestParam)
    assert param.location == "query"


def test_analyze_markedparam_with_plain_type():
    graph = Graph()
    seen = set()
    path_keys = ()

    # Use a plain type without annotation
    result = analyze_markedparam(graph, "name", seen, path_keys, str, None, MISSING)

    assert len(result) == 1
    name, param = result[0]
    assert name == "name"
    assert isinstance(param, RequestParam)
    assert param.location == "query"  # Default location


def test_analyze_markedparam_with_use_origin():
    graph = Graph()
    graph.node(SimpleDependency)
    seen = set()
    path_keys = ()

    use_type = Use[SimpleDependency]

    result = analyze_markedparam(graph, "dep", seen, path_keys, use_type)

    assert len(result) >= 1
    assert isinstance(result[0], DependentNode)


def test_analyze_param_union_no_payload():
    graph = Graph()
    seen = set()
    path_keys = ()

    union_type = Union[str, int, None]

    result = analyze_param(graph, "value", seen, path_keys, union_type, MISSING)

    assert len(result) == 1
    name, param = result[0]
    assert name == "value"
    assert isinstance(param, RequestParam)
    assert param.location == "query"


# Test for lines 237-238 - analyze_param with nested dependency in graph
def test_analyze_param_with_nested_dependency():
    graph = Graph()

    # Create a more complex dependency chain
    class DeepDependency:
        def __init__(self, value: str = "deep"):
            self.value = value

    class MiddleDependency:
        def __init__(self, deep: DeepDependency):
            self.deep = deep

    class TopDependency:
        def __init__(self, middle: MiddleDependency):
            self.middle = middle

    # Register all dependencies in the graph
    graph.node(DeepDependency)
    graph.node(MiddleDependency)
    graph.node(TopDependency)

    seen = set()
    path_keys = ()
    top_node = graph.analyze(TopDependency)
    result = analyze_param(graph, "top", seen, path_keys, TopDependency, MISSING)
    assert len(result) >= 1
    assert isinstance(result[0], DependentNode)
    result = analyze_nodeparams(top_node, graph, seen, path_keys)
    assert len(result) >= 1
    assert result[0] == top_node

    dep_types = [
        (
            type(node)
            if isinstance(node, DependentNode)
            else (
                node[1].type_
                if isinstance(node[1], (RequestParam, SingletonParam))
                else None
            )
        )
        for node in result
    ]
    assert TopDependency in dep_types or DependentNode in dep_types


def test_analyze_param_union_with_payload():
    graph = Graph()
    seen = set()
    path_keys = ()

    # Create a Union type that includes a Payload class and a non-Payload type
    union_type = Union[SamplePayload, int, None]

    result = analyze_param(graph, "mixed_data", seen, path_keys, union_type, MISSING)

    assert len(result) == 1
    name, param = result[0]
    assert name == "mixed_data"
    assert isinstance(param, RequestParam)

    # The key point: when a Union includes a Payload, it should be treated as a body parameter
    assert param.location == "body"

    # Test that the decoder can handle the union type
    # This indirectly tests that the decoder was created correctly in lines 237-238
    decoder = param.decoder
    assert decoder is not None


def test_textdecoder_factory_basic_types():
    """Test textdecoder_factory with basic types"""
    # Test with str
    str_decoder_func = textdecoder_factory(str)
    assert str_decoder_func("hello") == "hello"

    # Test with bytes
    bytes_decoder_func = textdecoder_factory(bytes)
    assert bytes_decoder_func(b"hello") == b"hello"

    # Test with int
    int_decoder_func = textdecoder_factory(int)
    assert int_decoder_func("42") == 42
    with pytest.raises(TypeError):
        assert int_decoder_func(42) == 42

    # Test with bool
    bool_decoder_func = textdecoder_factory(bool)
    assert bool_decoder_func("true") is True
    with pytest.raises(TypeError):
        assert bool_decoder_func(True) is True


def test_textdecoder_factory_with_bytes():
    """Test textdecoder_factory specifically with bytes type"""
    decoder = textdecoder_factory(bytes)

    # Test with bytes input
    assert decoder(b"hello world") == b"hello world"

    # Test with string input (should be converted to bytes)
    assert decoder("hello world") == b"hello world"


def test_textdecoder_factory_with_union_containing_bytes():
    """Test textdecoder_factory with unions containing bytes"""
    # Union of bytes and dict
    union_decoder = textdecoder_factory(Union[bytes, dict])

    # Should decode valid JSON as dict
    assert union_decoder(b'{"key": "value"}') == {"key": "value"}

    # Should keep invalid JSON as bytes
    assert union_decoder(b"not a json") == b"not a json"

    # Union of bytes, list and int
    complex_decoder = textdecoder_factory(Union[bytes, list, int])

    # Should decode valid JSON as list
    assert complex_decoder(b"[1, 2, 3]") == [1, 2, 3]

    # Should decode valid int
    assert complex_decoder(b"42") == 42

    # Should keep other content as bytes
    assert complex_decoder(b"hello") == b"hello"


def test_textdecoder_factory_with_union_types():
    """Test textdecoder_factory with various union types"""
    # Union with str
    str_union_decoder = textdecoder_factory(Union[str, int])
    assert str_union_decoder("42") == 42
    assert str_union_decoder("hello") == "hello"

    # Union with bytes
    bytes_union_decoder = textdecoder_factory(Union[bytes, dict])
    assert bytes_union_decoder(b'{"a": 1}') == {"a": 1}
    assert bytes_union_decoder(b"not json") == b"not json"

    # Complex union without str/bytes
    complex_decoder = textdecoder_factory(Union[int, list, dict])
    assert complex_decoder("42") == 42
    assert complex_decoder("[1, 2]") == [1, 2]
    assert complex_decoder('{"a": 1}') == {"a": 1}


def test_textdecoder_factory_with_python_3_10_union_syntax():
    """Test textdecoder_factory with Python 3.10+ union syntax (if supported)"""
    # Skip if UnionType is not available (Python < 3.10)
    if not hasattr(pytest, "skip_if"):
        try:
            # Python 3.10+ union syntax
            type_expr = eval("int | str")

            # Test with the new union syntax
            union_decoder = textdecoder_factory(type_expr)
            assert union_decoder("42") == 42
            assert union_decoder("hello") == "hello"
        except SyntaxError:
            pytest.skip("Python 3.10+ union syntax not supported")


def test_textdecoder_factory_with_optional():
    """Test textdecoder_factory with Optional types (Union[T, None])"""
    # Optional[int] is Union[int, None]
    optional_decoder = textdecoder_factory(int | None)

    assert optional_decoder("42") == 42
    assert optional_decoder("null") is None

    # Optional[bytes]
    optional_bytes_decoder = textdecoder_factory(bytes | None)

    assert optional_bytes_decoder(b"hello") == b"hello"
    assert optional_bytes_decoder("null") is None

def test_textdecoder_factory_with_complex_types():
    """Test textdecoder_factory with more complex types"""
    # List type
    list_decoder = textdecoder_factory(list[int])
    assert list_decoder("[1, 2, 3]") == [1, 2, 3]

    # Dict type
    dict_decoder = textdecoder_factory(dict[str, int])

    result = dict_decoder('{"a": 1, "b": 2}')


    assert result == {"a": 1, "b": 2}

    # Nested type
    nested_decoder = textdecoder_factory(list[dict[str, int]])
    assert nested_decoder('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]
