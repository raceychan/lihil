from typing import Literal

from lihil import HTTPException, Request, Response, status
from lihil.problems import collect_problems, get_solver, problem_solver


class CurentProblem(HTTPException[str]):
    "Aloha!"

    __status__ = 201


def test_collect_problems():
    problems = collect_problems()
    assert CurentProblem in problems


@problem_solver
def handle_404(req: Request, exc: Literal[404]) -> Response:
    return Response("resource not found", status_code=404)


assert get_solver(status.NOT_FOUND) is handle_404
