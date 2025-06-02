from functools import lru_cache
from typing import Any, Callable, get_origin

from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder
from pydantic import BaseModel

from lihil.interface import MISSING, IDecoder, IEncoder, Maybe, R, T

from lihil.utils.typing import lenient_issubclass


@lru_cache(256)
def decoder_factory(t: type[T], strict: bool = True) -> IDecoder[bytes, T]:
    if lenient_issubclass(t, BaseModel):
        return t.model_validate_json
    return JsonDecoder(t, strict=strict).decode


def encode_model(content: BaseModel) -> bytes:
    return content.__pydantic_serializer__.to_json(content)


@lru_cache(256)
def encoder_factory(
    t: Maybe[type[T]] = MISSING,
    enc_hook: Callable[[Any], R] | None = None,
    content_type: str = "json",
) -> IEncoder:
    if content_type == "text":
        return _encode_text

    origin_type = get_origin(t) or t

    if isinstance(origin_type, type):
        if issubclass(origin_type, BaseModel):
            return encode_model

    return JsonEncoder(enc_hook=enc_hook).encode


def _encode_text(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode()
