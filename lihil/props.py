from typing import Any, Literal, Sequence, TypedDict, Unpack

from msgspec import field

from lihil.auth.oauth import AuthBase
from lihil.interface import Record
from lihil.problems import DetailBase


class IEndpointProps(TypedDict, total=False):
    errors: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
    "Errors that might be raised from the current `endpoint`. These will be treated as responses and displayed in OpenAPI documentation."
    in_schema: bool
    "Whether to include this endpoint inside openapi docs"
    to_thread: bool
    "Whether this endpoint should be run wihtin a separate thread, only apply to sync function"
    scoped: Literal[True] | None
    "Whether current endpoint should be scoped"
    auth_scheme: AuthBase | None
    "Auth Scheme for access control"
    tags: Sequence[str]
    "OAS tag, endpoint with same tag will be grouped together"


class EndpointProps(Record, kw_only=True):
    errors: tuple[type[DetailBase[Any]], ...] = field(default_factory=tuple)
    to_thread: bool = True
    in_schema: bool = True
    scoped: Literal[True] | None = None
    auth_scheme: AuthBase | None = None
    tags: Sequence[str] | None = None

    @classmethod
    def from_unpack(cls, **iconfig: Unpack[IEndpointProps]):
        if raw_errors := iconfig.get("errors"):
            if not isinstance(raw_errors, Sequence):
                errors = (raw_errors,)
            else:
                errors = tuple(raw_errors)

            iconfig["errors"] = errors
        return cls(**iconfig)  # type: ignore
