from typing import Annotated

import pytest

from lihil import Request
from lihil.problems import problem_solver


async def test_random_problem_solver():

    def solve(req: Request, exc: Annotated[str, "aloha"]): ...

    with pytest.raises(TypeError):
        problem_solver(solve)
