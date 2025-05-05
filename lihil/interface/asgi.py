from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Literal,
    Mapping,
    MutableMapping,
    NotRequired,
    Protocol,
    TypedDict,
)

from starlette.datastructures import URL, Address, FormData
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


class IRequest(Protocol):
    def __init__(self, scope: IScope, receive: IReceive | None = None) -> None: ...
    def __getitem__(self, key: str) -> Any: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def __eq__(self, value: object) -> bool: ...
    def __hash__(self) -> int: ...
    @property
    def url(self) -> URL: ...
    @property
    def base_url(self) -> URL: ...
    @property
    def headers(self) -> Mapping[str, str]: ...
    @property
    def query_params(self) -> Mapping[str, str]: ...
    @property
    def path_params(self) -> Mapping[str, Any]: ...
    @property
    def cookies(self) -> Mapping[str, str]: ...
    @property
    def client(self) -> Address | None: ...
    @property
    def session(self) -> Mapping[str, Any]: ...
    @property
    def auth(self) -> Any: ...
    @property
    def user(self) -> Any: ...
    @property
    def state(self) -> dict[str, Any]: ...
    def url_for(self, name: str, /, **path_params: Any) -> URL: ...
    @property
    def method(self): ...
    @property
    def receive(self) -> IReceive: ...
    async def stream(self) -> AsyncGenerator[bytes, None]: ...
    async def body(self) -> bytes: ...
    async def json(self) -> Any: ...
    def form(
        self,
        *,
        max_files: int | float = 1000,
        max_fields: int | float = 1000,
        max_part_size: int = 1024 * 1024,
    ) -> AsyncContextManager[FormData]: ...
    async def close(self) -> None: ...
    async def is_disconnected(self) -> bool: ...
    async def send_push_promise(self, path: str) -> None: ...
