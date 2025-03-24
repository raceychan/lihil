from functools import lru_cache
from typing import Any, Callable, Union, get_args

from msgspec import DecodeError
from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder
from msgspec.json import encode as json_encode

from lihil.interface import IDecoder, IEncoder
from lihil.utils.typing import is_union_type


def to_str(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return content.decode()
    return content


def to_bytes(content: str | bytes) -> bytes:
    if isinstance(content, str):
        return content.encode()
    return content


def is_text_type(t: type) -> bool:

    if is_union_type(t):
        union_args = get_args(t)
        return any(u in (str, bytes) for u in union_args)

    return t in (str, bytes)


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

    def decode_reunion(content: bytes | str):
        try:
            res = rest_decoder(content)
        except DecodeError:
            return raw_decoder(content)
        return res

    return decode_reunion


@lru_cache(256)
def decoder_factory[T](t: type[T]) -> IDecoder[T]:
    if is_text_type(t):
        raise NotImplementedError("use textdecoder instead")
    return JsonDecoder(t).decode


@lru_cache(256)
def encoder_factory[R](enc_hook: Callable[[Any], R]) -> IEncoder[R]:
    return JsonEncoder(enc_hook=enc_hook).encode


encode_json = json_encode


def encode_text(content: bytes | str) -> bytes:
    if isinstance(content, str):
        return content.encode()
    return content
