from functools import lru_cache
from typing import Any, Callable

from msgspec import UNSET, UnsetType
from msgspec.json import Decoder as JsonDecoder
from msgspec.json import Encoder as JsonEncoder
from msgspec.json import schema_components

from lihil.interface import (
    MISSING,
    IDecoder,
    IEncoder,
    Maybe,
    R,
    RegularTypes,
    T,
    is_present,
)
from lihil.utils.typing import is_pydantic_model, is_text_type

SchemaHook = Callable[[type], dict[str, Any] | None] | None


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


MSGSPEC_REF_TEMPLATE = "#/components/schemas/{name}"
# NOTE: dont'change, as pydantic json schema would use it like `model=model` internally
PYDANTIC_REF_TEMPLATE = "#/components/schemas/{model}"


def _default_schema_hook(t: type) -> dict[str, Any] | None:
    if t is object:
        # Treat bare ``object`` annotations as unconstrained payloads.
        return {"type": "object"}
    return None


def _compose_hooks(schema_hook: SchemaHook | None) -> SchemaHook:
    if schema_hook is None:
        return _default_schema_hook
    else:

        def inner(t: type) -> dict[str, Any] | None:
            user_schema = schema_hook(t)
            if user_schema is not None:
                return user_schema
            return _default_schema_hook(t)

        return inner


def json_schema(
    type_: RegularTypes,
    schema_hook: SchemaHook = None,
    schema_generator: Maybe[Any] = MISSING,
) -> tuple[dict[str, Any], dict[str, Any]]:
    combined_hook: SchemaHook = _compose_hooks(schema_hook)

    if is_pydantic_model(type_):
        if is_present(schema_generator):
            schema = type_.model_json_schema(
                ref_template=PYDANTIC_REF_TEMPLATE, schema_generator=schema_generator
            )
        else:
            schema = type_.model_json_schema(ref_template=PYDANTIC_REF_TEMPLATE)
        defs = schema.pop("$defs", {})
    else:
        (schema,), defs = schema_components(
            (type_,),
            schema_hook=combined_hook,
            ref_template=MSGSPEC_REF_TEMPLATE,
        )
    return schema, defs


def is_json_compatible(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, list):
        return all(is_json_compatible(item) for item in value)
    if isinstance(value, tuple):
        return all(is_json_compatible(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and is_json_compatible(val)
            for key, val in value.items()
        )
    return False
