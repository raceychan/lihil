from typing import (
    Annotated,
    Any,
    Callable,
    Literal,
    Protocol,
    Self,
    dataclass_transform,
)

from msgspec import Struct
from msgspec.structs import asdict as struct_asdict
from msgspec.structs import replace as struct_replace

from lihil.interface.marks import EMPTY_RETURN_MARK
from lihil.vendor_types import FormData


class IDecoder[T](Protocol):
    def __call__(self, content: bytes, /) -> T: ...


class IFormDecoder[T](Protocol):
    def __call__(self, content: FormData, /) -> T: ...


class ITextDecoder[T](Protocol):
    "for non-body params"

    def __call__(self, content: str, /) -> T: ...


class IEncoder[T](Protocol):
    def __call__(self, content: T, /) -> bytes: ...


class Base(Struct):
    "Base Model for all internal struct, with Mapping interface implemented"

    def keys(self) -> tuple[str, ...]:
        return self.__struct_fields__

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def asdict(self):
        return struct_asdict(self)

    def replace(self, /, **changes: Any) -> Self:
        return struct_replace(self, **changes)


# @dataclass_transform(kw_only_default=True)
# class KWBase(Base, kw_only=True): ...


class ParamBase[T](Base):
    type_: type
    decoder: IDecoder[T]


@dataclass_transform(frozen_default=True)
class Record(Base, frozen=True, gc=False, cache_hash=True): ...  # type: ignore


@dataclass_transform(frozen_default=True)
class Payload(Record, frozen=True, gc=False):
    """
    a pre-configured struct that is frozen, gc_free
    """


class CustomEncoder(Base):
    encode: Callable[[Any], bytes]


class CustomDecoder(Base):
    """
    class IType: ...

    def decode_itype()


    async def create_user(i: Annotated[IType, CustomDecoder(decode_itype)])
    """

    decode: ITextDecoder[Any] | IDecoder[Any] | IFormDecoder[Any]


def empty_encoder(param: Any) -> bytes:
    return b""


type Empty = Annotated[Literal[None], CustomEncoder(empty_encoder), EMPTY_RETURN_MARK]
