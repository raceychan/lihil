# from types import GenericAlias, UnionType
from dataclasses import dataclass
from types import GenericAlias, UnionType
from typing import Any, Callable, ClassVar, Literal
from typing import Protocol as Protocol
from typing import TypeGuard, Union, get_args

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
from lihil.interface.marks import HTML as HTML
from lihil.interface.marks import Body as Body
from lihil.interface.marks import Cookie as Cookie
from lihil.interface.marks import Form as Form
from lihil.interface.marks import Header as Header
from lihil.interface.marks import Json as Json
from lihil.interface.marks import Path as Path
from lihil.interface.marks import Query as Query
from lihil.interface.marks import Resp as Resp
from lihil.interface.marks import Stream as Stream
from lihil.interface.marks import Text as Text
from lihil.interface.marks import Use as Use
from lihil.interface.marks import lhl_get_origin as lhl_get_origin
from lihil.interface.struct import Base as Base
from lihil.interface.struct import CustomDecoder as CustomDecoder
from lihil.interface.struct import CustomEncoder as CustomEncoder
from lihil.interface.struct import Empty as Empty
from lihil.interface.struct import IBodyDecoder as IBodyDecoder
from lihil.interface.struct import IDecoder as IDecoder
from lihil.interface.struct import IEncoder as IEncoder
from lihil.interface.struct import ITextDecoder as ITextDecoder
from lihil.interface.struct import Payload as Payload
from lihil.interface.struct import Record as Record

type ParamLocation = Literal["path", "query", "header", "body"]
type BodyContentType = Literal[
    "application/json", "multipart/form-data", "application/x-www-form-urlencoded"
]
type Func[**P, R] = Callable[P, R]

type Maybe[T] = T | "_Missed"

type StrDict = dict[str, Any]

type RegularTypes = type | UnionType | GenericAlias


def get_maybe_vars[T](m: Maybe[T]) -> T | None:
    return get_args(m)[0]


def is_provided[T](t: Maybe[T]) -> TypeGuard[T]:
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


type Unset[T] = UnsetType | T


def is_set[T](val: Unset[T]) -> TypeGuard[T]:
    return val is not UNSET


class ParamBase[T](Base):
    name: str
    type_: type[T] | UnionType
    location: ClassVar[ParamLocation]
    annotation: Any
    alias: str = ""
    default: Maybe[T] = MISSING
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

    def __repr__(self) -> str:
        name_repr = (
            self.name if self.alias == self.name else f"{self.name!r}, {self.alias!r}"
        )
        return f"{self.__class__.__name__}<{self.location}> ({name_repr}: {self.type_repr})"
