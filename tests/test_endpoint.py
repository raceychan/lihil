from typing import Annotated

import pytest
from ididi import Ignore, use
from starlette.requests import Request

from lihil import Json, Payload, Resp, Route
from lihil.constant import status
from lihil.errors import StatusConflictError


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


async def get_user(user_id: str) -> Annotated[Resp[str, status.NO_CONTENT], "hello"]:
    return "hello"


async def update_user(user_id: str) -> Annotated[dict[str, str], "aloha"]: ...


def test_return_status():
    rusers.post(create_user)
    ep = rusers.get_endpoint(create_user)
    assert any(qp[0] == "q" for qp in ep.deps.query_params)
    assert not any(qp[0] == "func_dep" for qp in ep.deps.query_params)
    assert any(pp[0] == "user_id" for pp in ep.deps.path_params)
    ep_ret = ep.deps.return_param
    assert ep_ret.status == 201


def test_status_conflict():
    with pytest.raises(StatusConflictError):
        rusers.get(get_user)


def test_annotated_generic():
    rusers.put(update_user)
    ep = rusers.get_endpoint(update_user)
    assert ep.deps.return_param.type_ == dict[str, str]
