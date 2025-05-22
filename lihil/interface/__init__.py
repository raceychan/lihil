# from types import GenericAlias, UnionType
from dataclasses import dataclass
from types import GenericAlias, UnionType
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Awaitable,
    Callable,
    Generic,
    Iterator,
    Literal,
    Mapping,
    ParamSpec,
    Protocol,
    TypeGuard,
    TypeVar,
    Union,
    get_args,
)

from msgspec import UNSET
from msgspec import Struct as Struct
from msgspec import UnsetType
from msgspec import field as field

from lihil.interface.asgi import HTTP_METHODS as HTTP_METHODS
from lihil.interface.asgi import ASGIApp as ASGIApp
from lihil.interface.asgi import IReceive as IReceive
from lihil.interface.asgi import IScope as IScope
from lihil.interface.asgi import ISend as ISend
from lihil.interface.asgi import MiddlewareFactory as MiddlewareFactory

# from lihil.interface.marks import AppState as AppState
from lihil.interface.marks import HTML as HTML
from lihil.interface.marks import Json as Json
from lihil.interface.marks import Stream as Stream
from lihil.interface.marks import Text as Text
from lihil.interface.struct import Base as Base
from lihil.interface.struct import CustomEncoder as CustomEncoder
from lihil.interface.struct import Empty as Empty
from lihil.interface.struct import IDecoder as IDecoder
from lihil.interface.struct import IEncoder as IEncoder
from lihil.interface.struct import Payload as Payload
from lihil.interface.struct import Record as Record

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")

ParamSource = Literal["path", "query", "header", "cookie", "body", "plugin"]
BodyContentType = Literal[
    "application/json", "multipart/form-data", "application/x-www-form-urlencoded"
]
Func = Callable[P, R]
IAsyncFunc = Callable[P, Awaitable[R]]


StrDict = dict[str, Any]
RegularTypes = type | UnionType | GenericAlias


def get_maybe_vars(m: T | "_Missed") -> T | None:
    exclude_maybe = tuple(m for m in get_args(m) if m is not _Missed)
    if exclude_maybe:
        return Union[exclude_maybe]
    return None


def is_provided(t: T | "_Missed") -> TypeGuard[T]:
    return t is not MISSING


@dataclass(frozen=True, repr=False)
class _Missed:

    __slots__ = ()

    __name__ = "liihl.MISSING"

    def __repr__(self):
        return "<lihil.MISSING>"

    def __bool__(self) -> Literal[False]:
        return False


MISSING = _Missed()

Maybe = _Missed | T
Unset = UnsetType | T


def is_set(val: UnsetType | T) -> TypeGuard[T]:
    return val is not UNSET


class ParamBase(Base, Generic[T]):
    name: str
    type_: type[T] | UnionType
    annotation: Any
    alias: str = ""
    default: T | _Missed = MISSING
    required: bool = False

    @property
    def type_repr(self) -> str:
        ty_origin = getattr(self.type_, "__origin__", None)
        raw_type_rerpr = repr(self.type_)
        if ty_origin is Union:
            type_repr = raw_type_rerpr.lstrip("typing.")
        else:
            type_repr = getattr(self.type_, "__name__", raw_type_rerpr)
        return type_repr

    def __post_init__(self):
        if not self.alias:
            self.alias = self.name
        self.required = self.default is MISSING


from starlette.datastructures import URL, FormData


class IAddress(Protocol):
    host: str
    port: int


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
    def headers(self) -> Mapping[str, str]: ...
    @property
    def query_params(self) -> Mapping[str, str]: ...
    @property
    def path_params(self) -> Mapping[str, Any]: ...
    @property
    def cookies(self) -> Mapping[str, str]: ...
    @property
    def client(self) -> IAddress | None: ...
    @property
    def state(self) -> dict[str, Any]: ...
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
