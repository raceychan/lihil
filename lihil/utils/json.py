from functools import lru_cache
from typing import Any, Callable

from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder
from msgspec.json import encode as msgspec_encode

from lihil.interface import MISSING, IDecoder, IEncoder, Maybe, R, T


@lru_cache(256)
def decoder_factory(t: type[T], strict: bool = True) -> IDecoder[bytes, T]:
    return JsonDecoder(t, strict=strict).decode


@lru_cache(256)
def encoder_factory(
    t: Maybe[type[T]] = MISSING,
    enc_hook: Callable[[Any], R] | None = None,
    content_type: str = "json",
) -> IEncoder:
    if content_type == "text":
        return _encode_text

    if t is MISSING:
        return adaptive_encoder

    return JsonEncoder(enc_hook=enc_hook).encode


def adaptive_encoder(content: Any) -> bytes:
    return msgspec_encode(content)


def _encode_text(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode()
