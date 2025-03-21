from typing import Annotated, Generator

import pytest
from ididi import Ignore, use
from starlette.requests import Request

from lihil import Json, Payload, Resp, Route, Stream
from lihil.constant import status
from lihil.errors import StatusConflictError
from lihil.plugins.testclient import LocalClient
from lihil.utils.threading import async_wrapper


class User(Payload, kw_only=True):
    id: int
    name: str
    email: str


# class Engine: ...


rusers = Route("users/{user_id}")


def add_q(q: str, user_id: str) -> Ignore[str]:
    return q


async def create_user(
    user: User,
    req: Request,
    user_id: str,
    func_dep: Annotated[str, use(add_q)],
) -> Resp[Json[User], status.CREATED]:
    return User(id=user.id, name=user.name, email=user.email)


def test_return_status():
    rusers.post(create_user)
    ep = rusers.get_endpoint(create_user)
    assert any(qp[0] == "q" for qp in ep.deps.query_params)
    assert not any(qp[0] == "func_dep" for qp in ep.deps.query_params)
    assert any(pp[0] == "user_id" for pp in ep.deps.path_params)
    ep_ret = ep.deps.return_param
    assert ep_ret.status == 201


def test_status_conflict():

    async def get_user(
        user_id: str,
    ) -> Annotated[Resp[str, status.NO_CONTENT], "hello"]:
        return "hello"

    with pytest.raises(StatusConflictError):
        rusers.get(get_user)


def test_annotated_generic():

    async def update_user(user_id: str) -> Annotated[dict[str, str], "aloha"]: ...

    rusers.put(update_user)
    ep = rusers.get_endpoint(update_user)
    repr(ep)
    assert ep.deps.return_param.type_ == dict[str, str]


def sync_func():
    return "ok"


async def test_async_wrapper():
    awrapped = async_wrapper(sync_func)
    assert await awrapped() == "ok"


async def test_async_wrapper_dummy():
    awrapped = async_wrapper(sync_func, threaded=False)
    assert await awrapped() == "ok"


async def test_ep_raise_httpexc():
    client = LocalClient()

    class UserNotFound(Exception): ...

    async def update_user(user_id: str) -> Annotated[dict[str, str], "aloha"]:
        raise UserNotFound()

    rusers = Route("users/{user_id}")
    rusers.put(update_user)

    ep = rusers.get_endpoint(update_user)
    with pytest.raises(UserNotFound):
        await client.call_endpoint(ep, path_params=dict(user_id=5))


async def test_sync_generator_endpoint():
    """Test an endpoint that returns a sync generator"""

    def stream_data() -> Stream[str]:
        """Return a stream of text data"""
        yield "Hello, "
        yield "World!"
        yield " This "
        yield "is "
        yield "a "
        yield "test."

    client = LocalClient()

    # Make the request
    route = Route("/stream")
    route.get(stream_data)

    ep = route.get_endpoint("GET")
    response = await client.call_endpoint(ep)

    # Check response status
    assert response.status_code == 200

    # Check content type
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    ans = ""

    async for res in response.stream():
        ans += res.decode()

    # Check the full response content
    assert ans == "Hello, World! This is a test."
