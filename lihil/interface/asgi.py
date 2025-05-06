from typing import (
    Any,
    Awaitable,
    Callable,
    Iterable,
    Literal,
    MutableMapping,
    NotRequired,
    TypedDict,
)

from starlette.types import Receive as IReceive
from starlette.types import Scope as IScope
from starlette.types import Send as ISend

# from msgspec.toml import decode
type HTTP_METHODS = Literal[
    "GET", "POST", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE", "PATCH", "CONNECT"
]


class ASGIVersions(TypedDict):
    spec_version: str
    version: Literal["3.0"]


class HTTPScope(TypedDict):
    type: Literal["http"]
    asgi: ASGIVersions
    http_version: str
    method: HTTP_METHODS
    scheme: str
    path: str
    raw_path: bytes
    query_string: bytes
    root_path: str
    headers: Iterable[tuple[bytes, bytes]]
    client: tuple[str, int] | None
    server: tuple[str, int | None] | None
    state: NotRequired[dict[str, Any]]
    extensions: NotRequired[dict[str, dict[object, object]]]


class LifespanScope(TypedDict):
    type: Literal["lifespan"]
    asgi: ASGIVersions
    state: NotRequired[dict[str, Any]]


# type IScope = Union[HTTPScope, LifespanScope]
type Message = MutableMapping[str, Any]


class LihilInterface:
    static_cache: dict[str, bytes]

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None: ...


ASGIApp = Callable[
    [
        IScope,
        IReceive,
        ISend,
    ],
    Awaitable[None],
]

type MiddlewareFactory[T: ASGIApp] = Callable[[T], ASGIApp]
