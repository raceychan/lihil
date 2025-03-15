from lihil import HTTPException
from lihil.problems import collect_problems


class CurentProblem(HTTPException[str]):
    "Aloha!"

    __status__ = 201


def test_collect_problems():
    problems = collect_problems()
    assert CurentProblem in problems
