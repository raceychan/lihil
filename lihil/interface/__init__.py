from typing import (
    Any,
    Callable,
    Literal,
    Protocol,
    Self,
    TypeGuard,
    dataclass_transform,
)

from msgspec import Struct as Struct
from msgspec import field as field
from msgspec.structs import asdict as struct_asdict
from msgspec.structs import fields as inspect_fields
from msgspec.structs import replace as struct_replace

from lihil.interface.asgi import HTTP_METHODS as HTTP_METHODS
from lihil.interface.asgi import ASGIApp as ASGIApp
from lihil.interface.asgi import IReceive as IReceive
from lihil.interface.asgi import IScope as IScope
from lihil.interface.asgi import ISend as ISend
from lihil.interface.asgi import MiddlewareFactory as MiddlewareFactory
from lihil.interface.marks import Body as Body
from lihil.interface.marks import Header as Header
from lihil.interface.marks import Json as Json
from lihil.interface.marks import Payload as Payload
from lihil.interface.marks import Query as Query
from lihil.interface.marks import Resp as Resp
from lihil.interface.marks import Stream as Stream
from lihil.interface.marks import Text as Text
from lihil.interface.marks import Use as Use

type ParamLocation = Literal["path", "query", "header", "body"]
type Func[**P, R] = Callable[P, R]

type Maybe[T] = T | "_Missed"


def is_provided[T](t: Maybe[T]) -> TypeGuard[T]:
    return t is not MISSING


class _Missed:
    __slots__ = ()

    __name__ = "MISSING"

    def __repr__(self):
        return "MISSING"

    def __bool__(self) -> Literal[False]:
        return False


MISSING = _Missed()


class ITextDecoder[T](Protocol):
    "Headers, URL are strings"

    def __call__(self, content: bytes | str, /) -> T: ...
class IDecoder[T](Protocol):
    def __call__(self, content: bytes | str, /) -> T: ...


class IEncoder[T](Protocol):
    def __call__(self, content: T, /) -> bytes: ...


# class IProblem[T](Protocol):
#     """
#     https://www.rfc-editor.org/rfc/rfc9457.html
#     """

#     @property
#     def type_(self) -> str: ...
#     @property
#     def title(self) -> str: ...
#     @property
#     def status(self) -> int: ...
#     @property
#     def detail(self) -> T: ...
#     @property
#     def instance(self) -> str: ...


@dataclass_transform(kw_only_default=True)
class Base(Struct, kw_only=True):
    "Base Model for all internal struct, with Mapping interface implemented"

    def keys(self) -> tuple[str, ...]:
        return self.__struct_fields__

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def asdict(self):
        return struct_asdict(self)

    def replace(self, /, **changes: Any) -> Self:
        return struct_replace(self, **changes)


class ParamBase[T](Base):
    type_: type
    decoder: IDecoder[T]


@dataclass_transform(frozen_default=True)
class Record(Base, frozen=True, cache_hash=True): ...


@dataclass_transform(frozen_default=True)
class FlatRecord(Record, frozen=True, cache_hash=True, gc=False): ...
