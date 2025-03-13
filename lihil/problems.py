from dataclasses import dataclass
from inspect import Parameter, signature
from types import MappingProxyType, UnionType
from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    Mapping,
    cast,
    get_args,
    get_origin,
)

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import Response

from lihil.constant import status
from lihil.interface import FlatRecord, IEncoder, ParamLocation
from lihil.utils.parse import to_kebab_case, trimdoc
from lihil.utils.phasing import encoder_factory
from lihil.utils.visitor import all_subclasses

"""
Unlike starlette, only sync error handler is allowed
user should just return response, we don't put it in threadpool as well.

If they want to do other things, do it with message bus
"""

type ExceptionHandler[Exc] = Callable[[Request, Exc], Response]
type ErrorRegistry = MappingProxyType[
    type[DetailBase[Any]] | int, ExceptionHandler[Any]
]


def __erresp_factory_registry():
    # TODO: handler can annoate return with Resp[Response, 404]
    handlers: dict[type[DetailBase[Any]] | int, ExceptionHandler[Any]] = {}

    def _extract_exception[Exc: DetailBase[Any]](
        handler: ExceptionHandler[Exc],
    ) -> type[DetailBase[Any]] | int | UnionType | int:
        sig = signature(handler)
        _, exc = sig.parameters.values()
        exc_annt = exc.annotation
        exc_type = get_origin(exc_annt) or exc_annt
        if exc_type is Parameter.empty:
            raise ValueError(f"handler {handler} has no annotation for {exc.name}")
        return exc_type

    def _catch[Exc: DetailBase[Any]](
        handler: ExceptionHandler[Exc],
    ) -> ExceptionHandler[Exc]:
        """\
        >>> @catch
        def any_error_handler(request: Request, exc: Exception | Literal[500]) -> ErrorResponse:
        """

        nonlocal handlers
        exc_type = _extract_exception(handler)
        exc_types = get_args(exc_type)

        if exc_types:
            for exctype in exc_types:
                handlers[exctype] = handler
        else:
            exc_type = cast(type[DetailBase[Any]] | int, exc_type)
            handlers[exc_type] = handler
        return handler

    return MappingProxyType(handlers), _catch


class ProblemDetail[T](FlatRecord):  # user can inherit this and extend it
    """
    ## Specification:
        - RFC 9457: https://www.rfc-editor.org/rfc/rfc9457.html

    This schema provides a standardized way to represent errors in HTTP APIs,
    allowing clients to understand error responses in a structured format.
    """

    type_: Annotated[
        str,
        Meta(
            description="A URI reference that identifies the type of problem.",
            examples=["user-not-Found"],
        ),
    ]
    status: Annotated[
        int,
        Meta(
            description="The HTTP status code for this problem occurrence.",
            examples=[404],
        ),
    ]
    title: Annotated[
        str,
        Meta(
            description="A short, human-readable summary of the problem type.",
            examples=[
                "The user you are looking for is either not created, or in-active"
            ],
        ),
    ]
    detail: Annotated[
        T,
        Meta(
            description="A human-readable explanation specific to this occurrence.",
            examples=["user info"],
        ),
    ]
    instance: Annotated[
        str,
        Meta(
            description="A URI reference identifying this specific problem occurrence.",
            examples=["/users/{user_id}"],
        ),
    ]


class DetailBase[T]:
    __slots__: tuple[str, ...] = ()
    __status__: ClassVar[status.Status]
    __problem_type__: ClassVar[str | None] = None
    __problem_title__: ClassVar[str | None] = None

    detail: T

    def __problem_detail__(self, instance: str) -> ProblemDetail[T]:
        raise NotImplementedError

    @classmethod
    def __json_example__(cls) -> dict[str, Any]:
        type_ = cls.__problem_type__ or to_kebab_case(cls.__name__)
        title = cls.__problem_title__ or trimdoc(cls.__doc__) or "Missing"
        status = cls.__status__
        return ProblemDetail[T](
            type_=type_,
            title=title,
            status=status,
            detail=cast(T, "Example detail for this error type"),
            instance="Example Instance for this error type",
        ).asdict()


class HTTPException[T](Exception, DetailBase[T]):
    """
    The base HTTP Exception class
    """

    __status__: ClassVar[status.Status] = status.code(status.UNPROCESSABLE_ENTITY)

    def __init__(
        self,
        detail: T = "MISSING",
        *,
        problem_status: status.Status | None = None,
        problem_detail_type: str | None = None,
        problem_detail_title: str | None = None,
    ):
        self.detail = detail
        self._problem_type = problem_detail_type
        self._problem_title = problem_detail_title
        self._problem_status: status.Status = problem_status or self.__status__
        super().__init__(detail)

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


class ErrorResponse[T](Response):
    problem_encoder = encoder_factory(ProblemDetail[T])

    def __init__(
        self,
        detail: ProblemDetail[T],
        status_code: int,
        headers: Mapping[str, str] | None = None,
        media_type: str = "application/problem+json",
    ):
        content = self.problem_encoder(detail)  # type: ignore
        super().__init__(
            content, status_code=status_code, headers=headers, media_type=media_type
        )


LIHIL_ERRESP_REGISTRY, catch = __erresp_factory_registry()
del __erresp_factory_registry


@catch
def default_error_catch(req: Request, exc: HTTPException[Any]) -> ErrorResponse[Any]:
    "User can override this to extend problem detail"
    detail = exc.__problem_detail__(req.url.path)
    return ErrorResponse[Any](detail, status_code=detail.status)


class ValidationProblem(FlatRecord):
    location: ParamLocation
    param: str
    message: str


class MissingRequestParam(ValidationProblem, tag=True):
    message: str = "Param is Missing"


class InvalidJsonReceived(ValidationProblem, tag=True):
    message: str = "Param value is not a valid json"


class InvalidDataType(ValidationProblem, tag=True):
    message: str = "Param is not of right type"


@dataclass(kw_only=True)
class InvalidRequestErrors:
    problem_encoder: ClassVar[IEncoder[Any]] = encoder_factory(list[ValidationProblem])
    __status__: ClassVar[int] = 422
    __problem_type__: ClassVar[str] = "invalid-request-errors"
    type: str = __problem_type__
    status: int = __status__
    title: str = "Check Your Params"
    instance: str = "uri of the entity"

    detail: list[ValidationProblem]

    @classmethod
    def __json_example__(cls) -> dict[str, Any]:
        result = ProblemDetail(
            type_=cls.type,
            title=cls.title,
            detail="Example Deatil",
            status=cls.__status__,
            instance=cls.instance,
        ).asdict()
        return result

    def __problem_detail__(
        self, instance: str
    ) -> ProblemDetail[list[ValidationProblem]]:
        return ProblemDetail(
            type_=self.type,
            title=self.title,
            detail=self.detail,
            status=self.__status__,
            instance=instance,
        )


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
