from typing import Annotated

import pytest
from ididi import Ignore, use
from starlette.requests import Request

from lihil import Json, Payload, Resp, Route
from lihil.constant import status
from lihil.interface.marks import Query


class User(Payload, kw_only=True):
    id: int
    name: str
    email: str


# class Engine: ...


rusers = Route("users/{user_id}")


def add_q(q: str, user_id: str) -> Ignore[str]:
    return q


@rusers.post
async def create_user(
    user: User,
    req: Request,
    func_dep: Annotated[str, use(add_q)],
) -> Resp[Json[User], status.CREATED]:
    return User(id=user.id, name=user.name, email=user.email)


def test_return_status():
    ep = rusers.get_endpoint(create_user)

    assert any(qp[0] == "q" for qp in ep.deps.query_params)
    assert not any(qp[0] == "func_dep" for qp in ep.deps.query_params)
    assert any(pp[0] == "user_id" for pp in ep.deps.path_params)
    ep_ret = ep.deps.return_param
    assert ep_ret.status == 201
