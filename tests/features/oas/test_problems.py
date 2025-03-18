from typing import List, Literal, Union

import pytest
from starlette.requests import Request

from lihil import HTTPException, Request, Response
from lihil import status as http_status
from lihil.constant import status as http_status
from lihil.problems import (
    DetailBase,
    ErrorResponse,
    HTTPException,
    ProblemDetail,
    collect_problems,
    get_solver,
    problem_solver,
)


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

    assert get_solver(http_status.NOT_FOUND) is handle_404
    assert get_solver(Literal[404]) is handle_404
    assert get_solver(404) is handle_404


def test_problem_solver_with_status():

    @problem_solver
    def handle_418(req: Request, exc: http_status.IM_A_TEAPOT) -> Response:
        return Response("resource not found", status_code=404)

    assert get_solver(http_status.IM_A_TEAPOT) is handle_418
    assert get_solver(Literal[418]) is handle_418
    assert get_solver(418) is handle_418


def test_problem_solver_with_exc():

    @problem_solver
    def handle_422(
        req: Request, exc: CurentProblem | http_status.UNSUPPORTED_MEDIA_TYPE
    ) -> Response:
        return Response("resource not found", status_code=404)

    assert get_solver(415) is handle_422
    assert get_solver(CurentProblem()) is handle_422


def test_problem_solver_with_many_exc():
    "where exc has a union of 3 or 4 exceptions"

    class Error1(HTTPException[str]):
        __status__ = http_status.code(http_status.NOT_FOUND)

    class Error2(HTTPException[str]):
        __status__ = http_status.code(http_status.BAD_REQUEST)

    class Error3(HTTPException[str]):
        __status__ = http_status.code(http_status.FORBIDDEN)

    class Error4(HTTPException[str]):
        __status__ = http_status.code(http_status.UNAUTHORIZED)

    def handle_multiple_errors(
        req: Request, exc: Union[Error1, Error2, Error3, Error4]
    ) -> ErrorResponse[str]:
        detail = exc.__problem_detail__(req.url.path)
        return ErrorResponse[str](detail, status_code=detail.status)

    problem_solver(handle_multiple_errors)


def test_unhanlde_exc_type():
    "where exc is annotated with a random class"

    class RandomClass:
        pass

    # This should raise an error during registration because RandomClass
    # is not a DetailBase subclass

    def handle_random_class(req: Request, exc: RandomClass) -> ErrorResponse[str]:
        return ErrorResponse[str](
            ProblemDetail(
                type_="error",
                title="Error",
                status=500,
                detail="Error",
                instance="/test",
            ),
            status_code=500,
        )

    with pytest.raises(NotImplementedError):
        problem_solver(handle_random_class)


def test_exc_missing_annotation():
    # Test that a handler without annotation raises ValueError
    with pytest.raises(ValueError):

        def handle_without_annotation(req: Request, exc) -> ErrorResponse[str]:
            return ErrorResponse[str](
                ProblemDetail(
                    type_="error",
                    title="Error",
                    status=500,
                    detail="Error",
                    instance="/test",
                ),
                status_code=500,
            )

        problem_solver(handle_without_annotation)


def test_a_random_exc_without_status():
    "test both when exc has not __status__ attribute and it has but not registered in status_handlers"

    # Case 1: Exception without __status__ attribute
    class NoStatusException(DetailBase[str]):
        def __init__(self, detail: str):
            self.detail = detail

        def __problem_detail__(self, instance: str) -> ProblemDetail[str]:
            return ProblemDetail[str](
                type_="no-status",
                title="No Status",
                status=500,
                detail=self.detail,
                instance=instance,
            )

    # Case 2: Exception with __status__ but not registered
    class UnregisteredStatusException(DetailBase[str]):
        __status__ = 599  # Custom status code not registered

        def __init__(self, detail: str):
            self.detail = detail

        def __problem_detail__(self, instance: str) -> ProblemDetail[str]:
            return ProblemDetail[str](
                type_="unregistered-status",
                title="Unregistered Status",
                status=self.__status__,
                detail=self.detail,
                instance=instance,
            )

    # Test that get_solver returns None for both cases
    no_status_exc = NoStatusException("No status")
    assert get_solver(no_status_exc) is None

    unreg_status_exc = UnregisteredStatusException("Unregistered status")
    assert get_solver(unreg_status_exc) is None


# def test_exc_is_detailbase():
#     "when exc is annotated exc: DetailBase"

#     @problem_solver
#     def handle_detail_base(req: Request, exc: DetailBase[Any]) -> ErrorResponse[Any]:
#         detail = exc.__problem_detail__(req.url.path)
#         return ErrorResponse[Any](detail, status_code=detail.status)

#     # Create a custom exception
#     class CustomException(HTTPException[str]):
#         __status__ = http_status.code(http_status.BAD_REQUEST)

#     # Test that our handler is used for any DetailBase subclass
#     mock_req = Request({"type": "http", "path": "/test"})
#     custom_exc = CustomException("Custom error")

#     handler = get_solver(custom_exc)
#     # assert handler is handle_detail_base

#     # Verify the handler works correctly
#     response = handler(mock_req, custom_exc)
#     assert isinstance(response, ErrorResponse)
#     assert response.status_code == http_status.code(http_status.BAD_REQUEST)


def test_call_httpexcpt__problem_detail__():
    "test if httpexception.__problem_detail__ works properly"

    # Test with default values
    exc = HTTPException("Test error")
    detail = exc.__problem_detail__("/test")

    assert isinstance(detail, ProblemDetail)
    assert detail.type_ == "http-exception"
    assert detail.status == http_status.code(http_status.UNPROCESSABLE_ENTITY)
    assert detail.detail == "Test error"
    assert detail.instance == "/test"

    # Test with custom values
    exc = HTTPException(
        "Custom error",
        problem_status=http_status.code(http_status.BAD_REQUEST),
        problem_detail_type="custom-error",
        problem_detail_title="Custom Error Title",
    )
    detail = exc.__problem_detail__("/custom")

    assert detail.type_ == "custom-error"
    assert detail.title == "Custom Error Title"
    assert detail.status == http_status.code(http_status.BAD_REQUEST)
    assert detail.detail == "Custom error"
    assert detail.instance == "/custom"


def test_parse_exception_not_implemented_error():
    """Test that parse_exception raises NotImplementedError for unsupported types"""

    from lihil.problems import parse_exception

    # Case 1: When exc_origin is None but not a TypeAliasType or HTTPException subclass
    class RegularClass:
        pass

    with pytest.raises(NotImplementedError):
        parse_exception(RegularClass)

    # Case 2: When exc_origin is not None and not one of the supported types
    # Using List, Dict, Set as examples of unsupported origin types
    with pytest.raises(NotImplementedError):
        parse_exception(List[str])

    with pytest.raises(NotImplementedError):
        parse_exception(dict[str, int])

    with pytest.raises(NotImplementedError):
        parse_exception(set[int])


