from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    Literal,
    Protocol,
    Self,
    dataclass_transform,
)

from msgspec import Struct
from msgspec.structs import asdict as struct_asdict
from msgspec.structs import replace as struct_replace

from lihil.interface import UNSET
from lihil.interface.marks import EMPTY_RETURN_MARK
from lihil.vendor_types import FormData


class IDecoder[I, T](Protocol):
    def __call__(self, content: I, /) -> T: ...


class IFormDecoder[T](Protocol):
    def __call__(self, content: FormData, /) -> T: ...


class IBodyDecoder[T](IDecoder[bytes, T]): ...


class ITextDecoder[T](IDecoder[str, T]):
    "for non-body params"


class IEncoder[T](Protocol):
    def __call__(self, content: T, /) -> bytes: ...


class Base(Struct):
    "Base Model for all internal struct, with Mapping interface implemented"

    __struct_defaults__: ClassVar[tuple[str]]

    def keys(self) -> tuple[str, ...]:
        return self.__struct_fields__

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def asdict(
        self, skip_defaults: bool = False, skip_unset: bool = False
    ) -> dict[str, Any]:
        if not skip_defaults and not skip_unset:
            return struct_asdict(self)

        if skip_defaults:  # unset is always default so we do not care
            vals: dict[str, Any] = {}
            for fname, default in zip(self.__struct_fields__, self.__struct_defaults__):
                val = getattr(self, fname)
                if val != default:
                    vals[fname] = val
            return vals
        else:
            return {
                f: val
                for f in self.__struct_fields__
                if (val := getattr(self, f)) is not UNSET
            }

    def replace(self, /, **changes: Any) -> Self:
        return struct_replace(self, **changes)

    def merge(self, other: Self) -> Self:
        "merge other props with current props, return a new props without modiying current props"
        vals = other.asdict(skip_defaults=True)
        merged = self.asdict() | vals
        return self.__class__(**merged)


# class ParamBase[T](Base):
#     type_: type
#     decoder: IDecoder[T]


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

    decode: ITextDecoder[Any] | IDecoder[Any, Any] | IFormDecoder[Any]


def empty_encoder(param: Any) -> bytes:
    return b""


type Empty = Annotated[Literal[None], CustomEncoder(empty_encoder), EMPTY_RETURN_MARK]
