from asyncio import get_running_loop
from contextlib import contextmanager
from typing import Union

import pytest

from lihil.lihil import ThreadPoolExecutor
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
