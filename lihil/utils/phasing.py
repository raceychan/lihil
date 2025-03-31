from functools import lru_cache
from typing import Any, Callable, Union

from msgspec import DecodeError
from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder
# from msgspec.json import encode as json_encode

# from lihil.errors import NotSupportedError
from lihil.interface import IDecoder, IEncoder


def to_str(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return content.decode()
    return content


def to_bytes(content: str | bytes) -> bytes:
    if isinstance(content, str):
        return content.encode()
    return content


def build_union_decoder(
    types: tuple[type], target_type: type[str | bytes]
) -> IDecoder[Any]:
    rest = tuple(t for t in types if t not in (bytes, str))

    if not rest:
        raise TypeError("union of str and bytes not supported")

    if len(rest) == 1:
        rest_decoder = decoder_factory(rest[0])
    else:
        new_union = Union[rest]  # type: ignore
        rest_decoder = decoder_factory(new_union)

    raw_decoder = to_str if target_type is str else to_bytes

    def decode_reunion(content: bytes):
        try:
            res = rest_decoder(content)
        except DecodeError:
            return raw_decoder(content)
        return res

    return decode_reunion


@lru_cache(256)
def decoder_factory[T](t: type[T], strict: bool = True) -> IDecoder[T]:
    return JsonDecoder(t, strict=strict).decode


@lru_cache(256)
def encoder_factory[R](enc_hook: Callable[[Any], R] | None = None) -> IEncoder[R]:
    return JsonEncoder(enc_hook=enc_hook).encode


encode_json = JsonEncoder().encode


def encode_text(content: bytes | str) -> bytes:
    if isinstance(content, str):
        return content.encode()
    return content
