from contextlib import contextmanager
from typing import Union

import pytest

from lihil.interface import MISSING, Base, Maybe, get_maybe_vars
from lihil.lihil import ThreadPoolExecutor
from lihil.utils.algorithms import deep_merge
from lihil.utils.json import encoder_factory
from lihil.utils.string import to_kebab_case

# from lihil.utils.threading import sync_ctx_to_thread
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


# async def test_sync_ctx_to_thread(workers: ThreadPoolExecutor):
#     new_ctx = sync_ctx_to_thread(
#         loop=get_running_loop(), workers=workers, cm=sync_ctx()
#     )

#     async with new_ctx as ctx:
#         assert ctx == 1


# async def test_fail_ctx(workers: ThreadPoolExecutor):
#     new_ctx = sync_ctx_to_thread(
#         loop=get_running_loop(), workers=workers, cm=sync_ctx_fail()
#     )

#     with pytest.raises(Exception):
#         async with new_ctx as ctx:
#             assert ctx == 1


def test_union_types():
    assert union_types([]) is None
    assert union_types([str]) is str

    new_u = union_types([int, str, bytes, list[int]])
    assert new_u == Union[int, str, bytes, list[int]]


def test_interface_utils():
    res = get_maybe_vars(Maybe[str | int])
    assert res == str | int
    assert get_maybe_vars(int) is None
    repr(MISSING)

    class MyBase(Base):
        name: str
        age: int

    mb = MyBase("1", 2)

    mbd = {**mb}
    assert mbd == {"name": "1", "age": 2}


def test_encode_test():
    encoder = encoder_factory(content_type="text")
    assert encoder(b"123") == b"123"
    assert encoder("123") == b"123"


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


def test_to_kebab_case():
    assert to_kebab_case("test") == "test"
    assert to_kebab_case("Test") == "test"
    assert to_kebab_case("TestTest") == "test-test"
    assert to_kebab_case("TestTestTest") == "test-test-test"
    assert to_kebab_case("TestTestTestTest") == "test-test-test-test"

    assert to_kebab_case("HTTPException") == "http-exception"
    assert to_kebab_case("UserAPI") == "user-api"
    assert to_kebab_case("OAuth2PasswordBearer") == "o-auth2-password-bearer"


def test_deep_merge():

    dict1 = {"a": 1, "b": {"c": 2, "d": 3}}
    dict2 = {"b": {"c": 4}, "e": 5}

    merged = deep_merge(dict1, dict2)
    assert merged == {"a": 1, "b": {"c": 4, "d": 3}, "e": 5}

    dict1 = {"a": [1, 2], "b": {"c": [3, 4]}}
    dict2 = {"a": [5], "b": {"c": [6]}}

    merged = deep_merge(dict1, dict2)
    assert merged == {"a": [1, 2, 5], "b": {"c": [3, 4, 6]}}

    # Test tuple and sets

    dict1 = {"a": (1, 2), "b": {"c": {3, 4}}}
    dict2 = {"a": (5,), "b": {"c": {6}}}
    merged = deep_merge(dict1, dict2)
    assert merged == {"a": (1, 2, 5), "b": {"c": {3, 4, 6}}}
