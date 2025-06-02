from functools import lru_cache
from typing import Any, Callable

from msgspec import UNSET, UnsetType
from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder
from pydantic import BaseModel, TypeAdapter

from lihil.interface import IDecoder, IEncoder, R, T
from lihil.utils.typing import should_use_pydantic


@lru_cache(256)
def decoder_factory(t: type[T], strict: bool = True) -> IDecoder[bytes, T]:
    if should_use_pydantic(t):
        return TypeAdapter(t).validate_json
    return JsonDecoder(t, strict=strict).decode


def encode_model(content: BaseModel) -> bytes:
    return content.__pydantic_serializer__.to_json(content)


@lru_cache(256)
def encoder_factory(
    t: type[T] | UnsetType = UNSET,
    enc_hook: Callable[[Any], R] | None = None,
    content_type: str = "json",
) -> IEncoder:
    if content_type == "text":
        return _encode_text

    if should_use_pydantic(t):
        return TypeAdapter(t).dump_json

    return JsonEncoder(enc_hook=enc_hook).encode


def _encode_text(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode()
