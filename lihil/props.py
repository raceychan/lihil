from typing import Any, Literal, Sequence, TypedDict

from msgspec import field
from typing_extensions import Unpack

from lihil.interface import IEncoder, Record

# from lihil.oas.model import OASResponse
from lihil.plugins import IPlugin
from lihil.plugins.auth.oauth import AuthBase
from lihil.problems import DetailBase


class IOASContent(TypedDict, total=False):
    "A map containing descriptions of potential response payloads"

    schema: dict[str, Any]
    "The schema defining the type used for the response"
    example: Any
    "An example of the response"
    examples: dict[str, Any]
    "Examples of the response"


class IOASResponse(TypedDict, total=False):
    description: str
    "A short description of the response"
    content: dict[str, Any]
    "A map containing descriptions of potential response payloads"


class IEndpointProps(TypedDict, total=False):
    problems: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
    "Errors that might be raised from the current `endpoint`. These will be treated as responses and displayed in OpenAPI documentation."
    in_schema: bool
    "Whether to include this endpoint inside openapi docs"
    to_thread: bool
    "Whether this endpoint should be run wihtin a separate thread, only apply to sync function"
    scoped: Literal[True] | None
    "Whether current endpoint should be scoped"
    auth_scheme: AuthBase | None
    "Auth Scheme for access control"
    tags: list[str] | None
    "OAS tag, endpoints with the same tag will be grouped together"
    encoder: IEncoder | None
    "Return Encoder"
    plugins: list[IPlugin]
    "Decorators to decorate the endpoint function"
    deps: list[Any] | None
    "Dependencies that might be used in "
    # responses: dict[int, OASResponse] | None
    # "Custom responses for OpenAPI documentation"


class EndpointProps(Record, kw_only=True):
    problems: list[type[DetailBase[Any]]] = field(
        default_factory=list[type[DetailBase[Any]]]
    )
    to_thread: bool = True
    in_schema: bool = True
    scoped: Literal[True] | None = None
    auth_scheme: AuthBase | None = None
    tags: list[str] | None = None
    encoder: IEncoder | None = None
    plugins: list[IPlugin] = field(default_factory=list[IPlugin])
    deps: list[Any] | None = None
    # responses: dict[int, OASResponse] | None = None

    @classmethod
    def from_unpack(cls, **iconfig: Unpack[IEndpointProps]):
        if problems := iconfig.get("problems"):
            if not isinstance(problems, Sequence):
                problems = [problems]

            iconfig["problems"] = problems
        return cls(**iconfig)  # type: ignore
