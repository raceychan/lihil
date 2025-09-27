from functools import lru_cache
from typing import Any, Callable

from msgspec import UNSET, UnsetType
from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder

from lihil.interface import IDecoder, IEncoder, R, T
from lihil.utils.typing import is_text_type, is_pydantic_model


@lru_cache(256)
def decoder_factory(t: type[T], strict: bool = True) -> IDecoder[bytes, T]:
    if is_pydantic_model(t):
        from pydantic import TypeAdapter

        return TypeAdapter(t).validate_json
    return JsonDecoder(t, strict=strict).decode


@lru_cache(256)
def encoder_factory(
    t: type[T] | UnsetType = UNSET,
    enc_hook: Callable[[Any], R] | None = None,
    content_type: str = "json",
) -> IEncoder:
    if content_type == "text":
        if t is UNSET or is_text_type(t):
            return _encode_text

    if is_pydantic_model(t):
        from pydantic import TypeAdapter

        return TypeAdapter(t).dump_json

    return JsonEncoder(enc_hook=enc_hook).encode


def _encode_text(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode()
