from asyncio import get_running_loop
from contextlib import contextmanager
from typing import Union

import pytest

from lihil.interface import MISSING, Base, Maybe, get_maybe_vars
from lihil.lihil import ThreadPoolExecutor
from lihil.utils.phasing import build_union_decoder, to_bytes, to_str, encode_text
from lihil.utils.threading import sync_ctx_to_thread
from lihil.utils.visitor import union_types


@pytest.fixture(scope="session")
def workers():
    return ThreadPoolExecutor(max_workers=2)


@contextmanager
def sync_ctx():
    yield 1


@contextmanager
def sync_ctx_fail():
    raise Exception
    yield


async def test_sync_ctx_to_thread(workers: ThreadPoolExecutor):
    new_ctx = sync_ctx_to_thread(
        loop=get_running_loop(), workers=workers, cm=sync_ctx()
    )

    async with new_ctx as ctx:
        assert ctx == 1


async def test_fail_ctx(workers: ThreadPoolExecutor):
    new_ctx = sync_ctx_to_thread(
        loop=get_running_loop(), workers=workers, cm=sync_ctx_fail()
    )

    with pytest.raises(Exception):
        async with new_ctx as ctx:
            assert ctx == 1


def test_union_types():
    assert union_types([]) is None
    assert union_types([str]) is str

    new_u = union_types([int, str, bytes, list[int]])
    assert new_u == Union[int, str, bytes, list[int]]


def test_interface_utils():
    res = get_maybe_vars(Maybe[str | int])
    assert res == str | int
    with pytest.raises(IndexError):
        assert get_maybe_vars(int) is None
    repr(MISSING)

    class MyBase(Base):
        name: str
        age: int

    mb = MyBase("1", 2)

    mbd = {**mb}
    assert mbd == {"name": "1", "age": 2}


def test_to_str_decode_bytes():
    assert to_str(b"abc") == "abc"


def test_to_bytes_decode_str():
    assert to_bytes("abc") == b"abc"


def test_byte_str_union():
    with pytest.raises(TypeError):
        build_union_decoder((bytes, str), target_type=str)


def test_build_union_decoder_with_complex_types():
    """Test union decoder with more complex types"""
    # Create a union decoder for Union[list, dict, str]
    union_decoder = build_union_decoder((list[int], dict[str, int], str), str)

    # Test decoding a valid list
    assert union_decoder("[1, 2, 3]") == [1, 2, 3]

    # Test decoding a valid dict
    assert union_decoder('{"a": 1, "b": 2}') == {"a": 1, "b": 2}

    # Test decoding a string that's not valid JSON
    assert union_decoder("not json") == "not json"


def test_build_union_decoder_nested_unions():
    """Test union decoder with nested union types"""
    # Define a nested union type
    NestedUnion = Union[int, Union[dict, list]]

    # Create a union decoder
    union_decoder = build_union_decoder((int, dict, list, str), str)

    # Test decoding different types
    assert union_decoder("42") == 42
    assert union_decoder('{"a": 1}') == {"a": 1}
    assert union_decoder("[1, 2, 3]") == [1, 2, 3]
    assert union_decoder("not json") == "not json"


def test_build_union_decoder_priority():
    """Test that the decoder tries complex types before falling back to str/bytes"""
    # Create a union decoder
    union_decoder = build_union_decoder((dict, str), str)

    # A valid JSON string that could be either a dict or kept as string
    json_str = '{"key": "value"}'

    # It should be decoded as a dict first
    assert union_decoder(json_str) == {"key": "value"}
    assert not isinstance(union_decoder(json_str), str)

    # A string that looks like JSON but isn't valid should be kept as string
    invalid_json = '{"key": value}'  # missing quotes around value
    assert union_decoder(invalid_json) == invalid_json
    assert isinstance(union_decoder(invalid_json), str)




def test_encode_test():
    assert encode_text(b"123") == b"123"
    assert encode_text("123") == b"123"
