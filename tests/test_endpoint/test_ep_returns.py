from inspect import Parameter
from typing import Annotated

import pytest

from lihil import Payload
from lihil.constant.status import OK
from lihil.signature.returns import (
    DEFAULT_RETURN,
    CustomEncoder,
    EndpointReturn,
    agen_encode_wrapper,
    parse_returns,
    parse_single_return,
    parse_status,
    syncgen_encode_wrapper,
)
from lihil.errors import InvalidStatusError, StatusConflictError, NotSupportedError
from lihil.interface.marks import HTML, Json, Resp, Stream, Text
from lihil.utils.typing import is_py_singleton


# Test parse_status function (lines 28, 32-35)
def test_parse_status():
    # Test with int (line 28)
    assert parse_status(200) == 200

    # Test with str (line 32)
    assert parse_status("201") == 201

    # Test with status code from constant module (lines 33-35)
    assert parse_status(OK) == 200

    # Test invalid type (line 37)
    with pytest.raises(InvalidStatusError, match="Invalid status code"):
        parse_status(None)


# Test CustomEncoder class (lines 57-58)
def test_custom_encoder():
    encoder = CustomEncoder(lambda x: f"encoded:{x}".encode())

    assert encoder.encode("test") == b"encoded:test"


# Test agen_encode_wrapper function (lines 75)
@pytest.mark.asyncio
async def test_agen_encode_wrapper():
    async def sample_agen():
        yield "test1"
        yield "test2"

    encoder = lambda x: f"encoded:{x}".encode()

    wrapped = agen_encode_wrapper(sample_agen(), encoder)

    results: list[bytes] = []
    async for item in wrapped:
        results.append(item)

    assert results == [b"encoded:test1", b"encoded:test2"]


# Test syncgen_encode_wrapper function (lines 93-94)
def test_syncgen_encode_wrapper():
    def sample_gen():
        yield "test1"
        yield "test2"

    encoder = lambda x: f"encoded:{x}".encode()

    wrapped = syncgen_encode_wrapper(sample_gen(), encoder)

    results = list(wrapped)

    assert results == [b"encoded:test1", b"encoded:test2"]


# Test EndpointReturn class (lines 102-103, 126, 131, 143-146, 151-152)
def test_return_param_init():
    # Test __post_init__ with valid status (line 102-103)
    param = EndpointReturn(encoder=lambda x: b"", status=200, type_=str)
    assert param.type_ == str

    # Test __post_init__ with invalid status (line 103)
    with pytest.raises(StatusConflictError):
        EndpointReturn(encoder=lambda x: b"", status=204, type_=str)

    param = EndpointReturn(
        type_=str, encoder=lambda x: b"", status=200, annotation="test"
    )
    assert "Return<test, 200>" in repr(param)


def test_return_param_from_mark():
    # Test with Text mark (line 131)
    param = parse_single_return(Text)
    assert "text/plain" in param.content_type
    assert param.type_ == bytes

    # Test with HTML mark (line 143-146)
    param = parse_single_return(HTML)
    assert "text/html" in param.content_type
    assert param.type_ == bytes

    # Test with Stream mark (line 151-152)
    param = parse_single_return(Stream[bytes])
    assert "text/event-stream" in param.content_type
    assert param.type_ == bytes

    # Test with Json mark
    param = parse_single_return(Json[dict])
    assert "application/json" in param.content_type

    # Test with Resp mark
    param = parse_single_return(Resp[str, 201])
    assert param.status == 201
    assert param.type_ == str


def test_return_param_from_annotated1():
    encoder = CustomEncoder(lambda x: f"custom:{x}".encode())

    param = parse_single_return(Annotated[str, encoder])
    assert param.type_ == str
    assert param.encoder == encoder.encode


def test_return_param_from_annotated2():
    encoder = CustomEncoder(lambda x: f"custom:{x}".encode())

    # Test with Annotated and Resp
    param = parse_single_return(Annotated[Resp[str, 201], encoder])
    assert param.status == 201
    assert param.type_ == str
    assert param.encoder == encoder.encode


# Test EndpointReturn.from_generic method (line 196)
def test_return_param_from_generic():
    # Test with non-resp mark, non-annotated type (line 196)
    param = parse_single_return(dict)
    assert param.type_ == dict
    assert param.status == 200

    # Test with Resp mark
    param = parse_single_return(Resp[str, 201])
    assert param.status == 201
    assert param.type_ == str

    # Test with Annotated
    encoder = CustomEncoder(lambda x: f"custom:{x}".encode())
    param = parse_single_return(Annotated[str, encoder])
    assert param.type_ == str


# Test is_py_singleton function (line 204)
def test_is_py_singleton():
    assert is_py_singleton(None) is True
    assert is_py_singleton(True) is True
    assert is_py_singleton(False) is True
    assert is_py_singleton(...) is True
    assert is_py_singleton(42) is False
    assert is_py_singleton("string") is False


def test_parse_return_with_no_status():
    res = parse_single_return(Resp[str])
    assert res.status == 200
    assert res.type_ == str


def test_empty_return():
    res = parse_single_return(Parameter.empty)
    assert res is DEFAULT_RETURN


def test_parse_returns():
    rets = parse_returns(Resp[str, 200] | Resp[int, 201])
    assert rets[200].type_ == str
    assert rets[201].type_ == int


class PublicUser(Payload):
    user_id: str
    user_email: str


def test_parse_jwt_return():
    from lihil.auth.jwt import JWTAuth

    with pytest.raises(NotSupportedError):
        rets = parse_returns(Resp[JWTAuth[Payload], 201])
