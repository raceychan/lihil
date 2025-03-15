import pytest

from lihil import HTTPException, Payload, Resp, Route, Text, status
from lihil.problems import collect_problems


class CurentProblem(HTTPException):
    "Aloha!"

    __status__ = 201


def test_collect_problems():
    problems = collect_problems()
    assert CurentProblem in problems



