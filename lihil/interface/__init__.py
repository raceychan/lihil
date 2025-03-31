from typing import Callable, Literal
from typing import Protocol as Protocol
from typing import TypeGuard, get_args

from msgspec import Struct as Struct
from msgspec import field as field

from lihil.interface.asgi import HTTP_METHODS as HTTP_METHODS
from lihil.interface.asgi import ASGIApp as ASGIApp
from lihil.interface.asgi import IReceive as IReceive
from lihil.interface.asgi import IScope as IScope
from lihil.interface.asgi import ISend as ISend
from lihil.interface.asgi import MiddlewareFactory as MiddlewareFactory
from lihil.interface.marks import HTML as HTML
from lihil.interface.marks import Body as Body
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
from lihil.interface.struct import IDecoder as IDecoder
from lihil.interface.struct import IEncoder as IEncoder
from lihil.interface.struct import ITextDecoder as ITextDecoder
from lihil.interface.struct import ParamBase as ParamBase
from lihil.interface.struct import Payload as Payload
from lihil.interface.struct import Record as Record

type ParamLocation = Literal["path", "query", "header", "body"]
type BodyContentType = Literal[
    "application/json", "multipart/form-data", "application/x-www-form-urlencoded"
]
type Func[**P, R] = Callable[P, R]

type Maybe[T] = T | "_Missed"


def get_maybe_vars[T](m: Maybe[T]) -> T | None:
    return get_args(m)[0]


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
