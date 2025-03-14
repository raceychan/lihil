from functools import lru_cache
from types import UnionType
from typing import Any, Callable, Union, get_args

from msgspec import DecodeError
from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder
from msgspec.json import encode as json_encode

from lihil.interface import IDecoder, IEncoder, ITextDecoder


def str_decoder(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return content.decode()
    return content


def bytes_decoder(content: str | bytes) -> bytes:
    return content.encode() if isinstance(content, str) else content


def is_text_type(t: type) -> bool:
    union_args = get_args(t)
    if not union_args:
        return t in (str, bytes)
    return any(u in (str, bytes) for u in union_args)


def build_union_decoder(
    types: tuple[type], target_type: type[str | bytes]
) -> IDecoder[Any]:
    rest = tuple(t for t in types if t not in (bytes, str))

    if not rest:
        raise TypeError("union of str and bytes not supported")

    if len(rest) == 1:
        rest_decoder = decoder_factory(rest[0])
    else:
        new_union = Union[*(rest)]  # type: ignore
        rest_decoder = decoder_factory(new_union)

    raw_decoder = str_decoder if target_type is str else bytes_decoder

    def decode_reunion(content: bytes | str):
        try:
            rest_decoder(content)
        except DecodeError:
            return raw_decoder(content)

    return decode_reunion


def textdecoder_factory(t: type | UnionType) -> ITextDecoder[Any] | IDecoder[Any]:
    union_args = get_args(t)
    if not union_args:
        if t is str:
            return str_decoder
        elif t is bytes:
            return bytes_decoder
        else:
            return decoder_factory(t)
    elif str in union_args:
        return build_union_decoder(union_args, str)
    elif bytes in union_args:
        return build_union_decoder(union_args, bytes)
    else:
        return decoder_factory(t)


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
