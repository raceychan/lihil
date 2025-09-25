from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    Generic,
    Literal,
    Protocol,
    TypeVar,
)

from msgspec import UNSET, Struct, UnsetType
from msgspec.json import encode as json_encode
from msgspec.structs import asdict as struct_asdict
from msgspec.structs import replace as struct_replace
from typing_extensions import Self, dataclass_transform

from lihil.interface.marks import EMPTY_RETURN_MARK, Stream
from lihil.utils.algorithms import deep_merge, deep_update
from lihil.vendors import FormData

I = TypeVar("I")
T = TypeVar("T")


DI = TypeVar("DI", contravariant=True)
DT = TypeVar("DT", covariant=True)


class IDecoder(Protocol, Generic[DI, DT]):
    def __call__(self, content: DI, /) -> DT: ...


class IEncoder(Protocol):
    def __call__(self, content: Any, /) -> bytes: ...


def exclude_value(data: Struct, value: Any) -> dict[str, Any]:
    return {
        f: val for f in data.__struct_fields__ if (val := getattr(data, f)) != value
    }


ITextualDecoder = IDecoder[str | list[str], T]
IBodyDecoder = IDecoder[bytes, T]
IFormDecoder = IDecoder[FormData, T]


class Base(Struct):
    "Base Model for all internal struct, with Mapping interface implemented"

    __struct_defaults__: ClassVar[tuple[str]]

    def keys(self) -> tuple[str, ...]:
        return self.__struct_fields__

    def __iter__(self):
        return iter(self.__struct_fields__)

    def __len__(self) -> int:
        return len(self.__struct_fields__)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def asdict(
        self,
        skip_defaults: bool = False,
        skip_unset: bool = False,
        skip_none: bool = False,
    ) -> dict[str, Any]:
        if not skip_defaults and not skip_unset and not skip_none:
            return struct_asdict(self)

        if skip_defaults:  # skip default would always skip unset
            vals: dict[str, Any] = {}
            for fname, default in zip(self.__struct_fields__, self.__struct_defaults__):
                val = getattr(self, fname)
                if val != default:
                    vals[fname] = val
            return vals
        elif skip_none:
            return exclude_value(self, None)
        else:
            return exclude_value(self, UNSET)

    def replace(self, /, **changes: Any) -> Self:
        return struct_replace(self, **changes)

    def merge(self, other: Self, deduplicate: bool = False) -> Self:
        "merge other props with current props, return a new props without modiying current props"
        vals = other.asdict(skip_defaults=True)
        merged = deep_merge(self.asdict(), vals, deduplicate=deduplicate)
        return self.__class__(**merged)

    def update(self, other: Self) -> Self:
        vals = other.asdict(skip_defaults=True)
        updated = deep_update(self.asdict(), vals)
        return self.__class__(**updated)


@dataclass_transform(frozen_default=True)
class Record(Base, frozen=True, gc=False, cache_hash=True): ...  # type: ignore


@dataclass_transform(frozen_default=True)
class Payload(Record, frozen=True, gc=False):
    """
    a pre-configured struct that is frozen, gc_free
    """


class CustomEncoder(Base):
    encode: Callable[[Any], bytes]


def empty_encoder(param: Any) -> bytes:
    return b""


class SSE(Record, kw_only=True):
    """
    Server-Sent Events (SSE) record type.
    """

    event: UnsetType | str = UNSET
    data: Any
    id: UnsetType | str = UNSET
    retry: UnsetType | int = UNSET


def encode_sse(sse: SSE, enc_hook: Callable[[Any], Any] | None = None) -> bytes:
    """
    Encode the SSE record to a string format.
    """

    lines: list[str] = []
    if sse.event is not UNSET:
        lines.append(f"event: {sse.event}")
    if sse.id is not UNSET:
        lines.append(f"id: {sse.id}")
    if sse.retry is not UNSET:
        lines.append(f"retry: {sse.retry}")

    # Ensure data is a string (JSON encode if not already a string)
    payload = (
        sse.data
        if isinstance(sse.data, str)
        else json_encode(sse.data, enc_hook=enc_hook).decode()
    )

    payload_lines = payload.splitlines()
    for line in payload_lines:
        lines.append(f"data: {line}")

    content = "\n".join(lines) + "\n\n"
    return content.encode()


Empty = Annotated[Literal[None], CustomEncoder(empty_encoder), EMPTY_RETURN_MARK]

EventStream = Annotated[Stream[SSE], CustomEncoder(encode_sse)]
