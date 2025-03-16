from typing import Literal

from lihil import HTTPException, Request, Response, status
from lihil.problems import collect_problems, get_solver, problem_solver


class CurentProblem(HTTPException[str]):
    "Aloha!"

    __status__ = 422


def test_collect_problems():
    problems = collect_problems()
    assert CurentProblem in problems


def test_problem_solver_with_literal():

    @problem_solver
    def handle_404(req: Request, exc: Literal[404]) -> Response:
        return Response("resource not found", status_code=404)

    assert get_solver(status.NOT_FOUND) is handle_404
    assert get_solver(Literal[404]) is handle_404
    assert get_solver(404) is handle_404


def test_problem_solver_with_status():

    @problem_solver
    def handle_418(req: Request, exc: status.IM_A_TEAPOT) -> Response:
        return Response("resource not found", status_code=404)

    assert get_solver(status.IM_A_TEAPOT) is handle_418
    assert get_solver(Literal[418]) is handle_418
    assert get_solver(418) is handle_418


def test_problem_solver_with_exc():

    @problem_solver
    def handle_422(
        req: Request, exc: CurentProblem | status.UNSUPPORTED_MEDIA_TYPE
    ) -> Response:
        return Response("resource not found", status_code=404)

    assert get_solver(415) is handle_422
    assert get_solver(CurentProblem()) is handle_422
