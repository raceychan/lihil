from inspect import Parameter
from typing import Annotated

import pytest

from lihil import Payload, status
from lihil.errors import InvalidStatusError, StatusConflictError
from lihil.interface.marks import HTML, Json, Stream, Text
from lihil.signature.returns import (
    DEFAULT_RETURN,
    CustomEncoder,
    EndpointReturn,
    agen_encode_wrapper,
    parse_returns,
    parse_status,
    syncgen_encode_wrapper,
)
from lihil.utils.typing import is_py_singleton


# Test parse_status function (lines 28, 32-35)
def test_parse_status():
    # Test with int (line 28)
    assert parse_status(200) == 200

    # Test with str (line 32)
    assert parse_status("201") == 201

    # Test with status code from constant module (lines 33-35)
    assert parse_status(status.OK) == 200

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
    param = parse_returns(Text)[200]
    assert "text/plain" == param.content_type
    assert param.type_ == bytes

    # Test with HTML mark (line 143-146)
    param = parse_returns(HTML)[200]
    assert "text/html" == param.content_type
    assert param.type_ == bytes

    # Test with Stream mark (line 151-152)
    param = parse_returns(Stream[bytes])[200]
    assert "text/event-stream" == param.content_type
    assert param.type_ == bytes

    # Test with Json mark
    param = parse_returns(Json[dict])[200]
    assert "application/json" == param.content_type

    # Test with Resp mark
    param = parse_returns(Annotated[str, status.CREATED])
    assert param[201].type_ == str


def test_return_param_from_annotated1():
    encoder = CustomEncoder(lambda x: f"custom:{x}".encode())

    param = parse_returns(Annotated[str, encoder])[200]
    assert param.type_ == str
    assert param.encoder == encoder.encode


def test_return_param_from_annotated2():
    encoder = CustomEncoder(lambda x: f"custom:{x}".encode())

    # Test with Annotated and Resp
    param = parse_returns(Annotated[Annotated[str, status.CREATED], encoder])[201]
    assert param.type_ == str
    assert param.encoder == encoder.encode


# Test EndpointReturn.from_generic method (line 196)
def test_return_param_from_generic():
    # Test with non-resp mark, non-annotated type (line 196)
    param = parse_returns(dict)[200]
    assert param.type_ == dict
    assert param.status == 200

    # Test with Resp mark
    param = parse_returns(Annotated[str, status.CREATED])[201]
    assert param.status == 201
    assert param.type_ == str

    # Test with Annotated
    encoder = CustomEncoder(lambda x: f"custom:{x}".encode())
    param = parse_returns(Annotated[str, encoder])[200]
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
    res = parse_returns(str)[200]
    assert res.status == 200
    assert res.type_ == str


def test_empty_return():
    res = parse_returns(Parameter.empty)[200]
    assert res is DEFAULT_RETURN


def test_parse_returns():
    rets = parse_returns(Annotated[str, status.OK] | Annotated[int, status.CREATED])
    assert rets[200].type_ == str
    assert rets[201].type_ == int


class PublicUser(Payload):
    user_id: str
    user_email: str
