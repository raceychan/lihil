from functools import lru_cache
from typing import Any, Callable

from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder

from lihil.interface import IDecoder, IEncoder, T, R


@lru_cache(256)
def decoder_factory(t: type[T], strict: bool = True) -> IDecoder[bytes, T]:
    return JsonDecoder(t, strict=strict).decode


@lru_cache(256)
def encoder_factory(enc_hook: Callable[[Any], R] | None = None) -> IEncoder[R]:
    return JsonEncoder(enc_hook=enc_hook).encode


encode_json = encoder_factory()


def encode_text(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode()
