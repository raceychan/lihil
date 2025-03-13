from lihil.problems import HTTPException, collect_problems


class CurentProblem(HTTPException):
    "Aloha!"
    __status__ = 201


def test_collect_problems():
    problems = collect_problems()
    assert CurentProblem in problems
