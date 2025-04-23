from asyncio import get_running_loop
from contextlib import contextmanager
from typing import Literal, Union

import pytest

from lihil import Graph, Header
from lihil.errors import NotSupportedError
from lihil.interface import MISSING, Base, Maybe, get_maybe_vars
from lihil.lihil import ThreadPoolExecutor
from lihil.signature.params import ParamParser
from lihil.utils.json import encode_text
from lihil.utils.string import parse_header_key
from lihil.utils.threading import sync_ctx_to_thread
from lihil.utils.typing import union_types


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


def test_encode_test():
    assert encode_text(b"123") == b"123"
    assert encode_text("123") == b"123"


def test_parse_header_key():
    assert parse_header_key("AuthToken", None) == "auth-token"

    parser = ParamParser(graph=Graph())

    with pytest.raises(NotSupportedError):
        parser.parse_param("test", Header[str, 5])

    with pytest.raises(NotSupportedError):
        parser.parse_param("test", Header[str, Literal[5]])


def test_payload_replace():
    class User(Base):
        user_name: str

    user = User("user")
    assert user.replace(user_name="new").user_name == "new"


def test_payload_skip_none():
    class User(Base):
        user_name: str
        age: int | None = None

    assert "age" not in User("user").asdict(skip_none=True)
