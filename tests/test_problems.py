from typing import Annotated

import pytest

from lihil import Request, status
from lihil.problems import InvalidAuthError, parse_exception, problem_solver


async def test_random_problem_solver():

    def solve(req: Request, exc: Annotated[str, "aloha"]): ...

    with pytest.raises(TypeError):
        problem_solver(solve)


def test_parse_exc():
    with pytest.raises(TypeError):
        parse_exception(Annotated[int, status.NOT_FOUND])

    with pytest.raises(TypeError):
        parse_exception(5)


def test_raise_invalid_auth():
    ae = InvalidAuthError()
    assert ae.headers and ae.headers["WWW-Authenticate"] == "Bearer"
