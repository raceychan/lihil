from typing import Annotated, Any, ClassVar, cast, Generic

from msgspec import Meta

from lihil.constant import status as http_status
from lihil.interface.struct import Record
from lihil.interface import T
from lihil.utils.string import to_kebab_case, trimdoc


# =========
class ProblemDetail(Record, Generic[T]):  # user can inherit this and extend it
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


class DetailBase(Generic[T]):
    __slots__: tuple[str, ...] = ()
    __status__: ClassVar[http_status.Status]
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
