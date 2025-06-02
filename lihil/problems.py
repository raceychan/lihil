from functools import lru_cache
from inspect import Parameter, signature
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    Literal,
    Mapping,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

from typing_extensions import TypeAliasType

from lihil.constant import status as http_status
from lihil.interface import ParamSource, Record, T
from lihil.interface.problem import DetailBase, ProblemDetail
from lihil.utils.json import encoder_factory
from lihil.utils.string import to_kebab_case, trimdoc
from lihil.utils.typing import all_subclasses, is_union_type, lenient_issubclass
from lihil.vendors import Request, Response  # , WebSocket

"""
Unlike starlette, only sync error handler is allowed
user should just return response, we don't put it in threadpool as well.

If they want to do other things, do it with message bus
"""
Exc = TypeVar("Exc")

ExceptionHandler = Callable[[Request, Exc], Response]
ErrorRegistry = MappingProxyType[
    "type[DetailBase[Any]] | http_status.Status", ExceptionHandler[Any]
]


def parse_exception(
    exc: type["DetailBase[Any]"] | TypeAliasType,
) -> type["DetailBase[Any]"] | int | list[type["DetailBase[Any]"] | int]:
    exc_origin = get_origin(exc)

    if exc_origin is None:
        if lenient_issubclass(exc, HTTPException):
            return exc
        elif http_status.is_status(exc):
            return http_status.code(exc)
        raise TypeError(f"Invalid exception type {exc}")
    elif exc_origin is Literal:
        while isinstance(exc, TypeAliasType):
            exc = exc.__value__
        return get_args(exc)[0]
    elif is_union_type(exc):
        res: list[Any] = []
        sub_excs = get_args(exc)
        for e in sub_excs:
            sub_r = parse_exception(e)
            res.append(sub_r)
        return res
    else:
        if not isinstance(exc, type):
            exc_local = exc_origin
        else:
            exc_local = exc

        if lenient_issubclass(exc_origin, DetailBase) or lenient_issubclass(
            exc_local, DetailBase
        ):
            # if exc is a subclass of DetailBase then tha
            return cast(type["DetailBase[Any]"], exc_origin)
        raise TypeError(f"Invalid exception type {exc}")


DExc = TypeVar("DExc", bound=DetailBase[Any] | http_status.Status)


def __erresp_factory_registry():
    # TODO: handler can annoate return with Resp[Response, 404]
    exc_handlers: dict[type[DetailBase[Any]], ExceptionHandler[Any]] = {}
    status_handlers: dict[int, ExceptionHandler[Any]] = {}

    def _extract_exception(
        handler: ExceptionHandler[DExc],
    ) -> type[DetailBase[Any]] | int | list[type[DetailBase[Any]] | int]:
        sig = signature(handler)
        _, exc = sig.parameters.values()
        exc_annt = exc.annotation

        if exc_annt is Parameter.empty:
            raise ValueError(f"handler {handler} has no annotation for {exc.name}")

        return parse_exception(exc_annt)

    def _solver(
        handler: ExceptionHandler[DExc],
    ) -> ExceptionHandler[DExc]:
        """\
        >>>
        @solver
        def any_error_handler(request: Request, exc: Exception | Literal[500]) -> ErrorResponse:
        """

        nonlocal exc_handlers, status_handlers
        exc_type = _extract_exception(handler)

        if isinstance(exc_type, list):
            for exc in exc_type:
                if isinstance(exc, int):
                    status_handlers[exc] = handler
                else:
                    exc_handlers[exc] = handler
        else:
            if isinstance(exc_type, int):
                status_handlers[exc_type] = handler
            else:
                exc_handlers[exc_type] = handler
        return handler

    @lru_cache
    def get_solver(
        exc: DetailBase[Any] | int | http_status.Status | TypeAliasType,
    ) -> ExceptionHandler[Exception] | None:
        nonlocal status_handlers, exc_handlers

        if isinstance(exc, int):
            return status_handlers.get(exc)
        elif isinstance(exc, TypeAliasType):
            return status_handlers.get(http_status.code(exc))
        elif get_origin(exc) is Literal:
            scode: int = get_args(exc)[0]
            return status_handlers.get(scode)

        for base in type(exc).__mro__:
            if res := exc_handlers.get(base):
                return res
        try:
            code = exc.__status__  # type: ignore
            return status_handlers[code]
        except AttributeError:
            pass
        except KeyError:
            pass

    def default_error_catch(
        req: Request, exc: HTTPException[Any]
    ) -> ErrorResponse[Any]:
        "User can override this to extend problem detail"
        detail = exc.__problem_detail__(req.url.path)
        return ErrorResponse[Any](
            detail, status_code=detail.status, headers=exc.headers
        )

    # TODO: default ws catch
    _solver(default_error_catch)
    return MappingProxyType(exc_handlers), _solver, get_solver


class HTTPException(Exception, DetailBase[T]):
    """
    Something Wrong with the client request.
    """

    __status__: ClassVar[http_status.Status] = http_status.code(
        http_status.UNPROCESSABLE_ENTITY
    )
    # TODO: let user provide example in classvar and display it in oas schema

    def __init__(
        self,
        detail: T = "MISSING",
        *,
        headers: dict[str, str] | None = None,
        problem_status: TypeAliasType | http_status.Status | None = None,
        problem_detail_type: str | None = None,
        problem_detail_title: str | None = None,
    ):
        self.detail = detail
        self.headers = headers
        self._problem_type = problem_detail_type
        self._problem_title = problem_detail_title
        if problem_status:
            if isinstance(problem_status, int):
                self._problem_status: http_status.Status = problem_status
            else:
                self._problem_status = http_status.code(problem_status)
        else:
            self._problem_status = self.__status__
        super().__init__(detail)

    @property
    def status(self) -> int:
        return self._problem_status

    def __problem_detail__(self, instance: str) -> ProblemDetail[T]:
        """
        User can override this to extend problem detail
        """
        problem_type = (
            self._problem_type
            or self.__problem_type__
            or to_kebab_case(self.__class__.__name__)
        )
        problem_title = (
            self._problem_title
            or trimdoc(self.__doc__)
            or self.__problem_title__
            or "Missing"
        )
        problem_status = self._problem_status or self.__status__

        return ProblemDetail[T](
            type_=problem_type,
            title=problem_title,
            status=problem_status,
            detail=self.detail,
            instance=instance,
        )


class ErrorResponse(Response, Generic[T]):
    encoder = None

    def __init__(
        self,
        detail: ProblemDetail[T],
        status_code: int,
        headers: Mapping[str, str] | None = None,
        media_type: str = "application/problem+json",
    ):
        if self.encoder is None:
            self.encoder = encoder_factory(type(detail))
        content = self.encoder(detail)
        super().__init__(
            content, status_code=status_code, headers=headers, media_type=media_type
        )


LIHIL_ERRESP_REGISTRY, problem_solver, get_solver = __erresp_factory_registry()
del __erresp_factory_registry


class CustomValidationError(HTTPException[T]):
    detail: str = "custom decoding errro"


# ================== Data Validtion ================
class ValidationProblem(Record):
    location: ParamSource
    param: str
    message: str


class MissingRequestParam(ValidationProblem, tag=True):
    message: str = "Param is Missing"


class InvalidJsonReceived(ValidationProblem, tag=True):
    message: str = "Param value is not a valid json"


class InvalidDataType(ValidationProblem, tag=True):
    message: str = "Param is not of right type"


class InvalidFormError(ValidationProblem, tag=True):
    message: str = "Form is not valid"


class CustomDecodeErrorMessage(ValidationProblem, tag=True):
    message: str


class InvalidRequestErrors(HTTPException[list[ValidationProblem]]):
    "Check Your Params"


# ================== Data Validtion ================


# ================== Auth Validtion ================


class InvalidAuthError(HTTPException[str]):
    "We received your credential but could not validate it"

    __status__ = 401

    def __init__(self, detail: str = "Invalid Credentials", scheme: str = "Bearer"):
        super().__init__(detail=detail, headers={"WWW-Authenticate": scheme})
        assert self.headers is not None


# ================== Auth Validtion ================


def collect_problems() -> list[type]:
    """
    Collect all problem classes from the error registry.

    Args:
        error_registry: The registry containing error classes

    Returns:
        A list of all problem classes
    """

    problems = list(all_subclasses(DetailBase))
    return problems
