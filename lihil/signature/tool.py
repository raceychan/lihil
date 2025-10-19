from collections.abc import Mapping
from copy import deepcopy
from inspect import Parameter, Signature, signature
from types import UnionType
from typing import Annotated, Any, Callable

from ididi.config import IGNORE_PARAM_MARK, USE_FACTORY_MARK

from lihil.errors import InvalidParamError, NotSupportedError
from lihil.interface import MISSING, Maybe, Record, is_present
from lihil.utils.json import encoder_factory, is_json_compatible, json_schema
from lihil.utils.typing import get_origin_pro

from .params import ParamMeta

from msgspec import Struct, convert, field
from msgspec.json import Decoder as JsonDecoder
from msgspec.structs import asdict as struct_asdict

try:  # pragma: no cover - optional dependency
    from pydantic import BaseModel as PydanticBaseModel
except ImportError:  # pragma: no cover - optional dependency
    PydanticBaseModel = None


_JSON_ENCODER = encoder_factory()
_JSON_DECODER = JsonDecoder()


class ToolParameter(Record):
    name: str
    alias: str
    schema: dict[str, Any]
    required: bool
    type_hint: type[Any] | UnionType
    default: Maybe[Any] = MISSING


class ToolSignature(Record):
    name: str
    description: str | None
    parameters: dict[str, ToolParameter]
    return_type: str
    payload_struct: type[Struct]

    def to_openai_tool(self) -> dict[str, Any]:
        """
        Returns the tool signature in the format expected by OpenAI's function calling.
        {
            "type": "function",
            "function": {
                "name": "get_horoscope",
                "description": "Get today's horoscope for an astrological sign.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sign": {
                            "type": "string",
                            "description": "An astrological sign like Taurus or Aquarius",
                        },
                    },
                    "required": ["sign"],
                },
            },
        },
        """
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in self.parameters.values():
            properties[param.alias] = param.schema
            if param.required:
                required.append(param.alias)

        parameters: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            parameters["required"] = required

        function_block: dict[str, Any] = {
            "name": self.name,
            "parameters": parameters,
        }
        if self.description:
            function_block["description"] = self.description
        return {"type": "function", "function": function_block}

    def encode_params(self, data: Mapping[str, Any] | Struct, /) -> bytes:
        if isinstance(data, self.payload_struct):
            obj = data
        elif isinstance(data, Mapping):
            kwargs: dict[str, Any] = {}
            for name, param in self.parameters.items():
                if param.alias in data:
                    kwargs[name] = data[param.alias]
                elif name in data:
                    kwargs[name] = data[name]
            obj = self.payload_struct(**kwargs)
        else:
            raise TypeError(
                "data must be a mapping or an instance of the tool payload struct"
            )
        payload: dict[str, Any] = {}
        for name, param in self.parameters.items():
            value = getattr(obj, name)
            json_value = _to_plain_json(value)
            if not is_json_compatible(json_value):
                json_value = None
            payload[param.alias] = json_value
        return _JSON_ENCODER(payload)

    def decode_params(self, payload: bytes | str) -> Struct:
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        return _decode_params(payload, self)


class ToolParser:
    def parse(self, func: Callable[..., Any]) -> ToolSignature:
        func_sig = signature(func)
        parameters: dict[str, ToolParameter] = {}

        seen_aliases: set[str] = set()
        for param in func_sig.parameters.values():
            if param.kind in (
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
            ):
                raise NotSupportedError(
                    f"Parameter kind {param.kind!r} is not supported for tool parsing"
                )

            parsed = self._parse_param(param)
            if parsed is None:
                continue

            if parsed.alias in seen_aliases:
                raise InvalidParamError(
                    f"Duplicated parameter alias detected: {parsed.alias!r}"
                )
            seen_aliases.add(parsed.alias)
            parameters[parsed.name] = parsed

        description = func.__doc__.strip() if func.__doc__ else None
        payload_struct = _build_struct(func.__name__, parameters)
        return ToolSignature(
            name=func.__name__,
            description=description,
            parameters=parameters,
            return_type=self._format_return(func_sig.return_annotation),
            payload_struct=payload_struct,
        )

    def _parse_param(self, param: Parameter) -> ToolParameter | None:
        default: Maybe[Any]
        if param.default is Parameter.empty:
            default = MISSING
        else:
            default = param.default

        annotation = (
            param.annotation if param.annotation is not Parameter.empty else Any
        )
        base_type, metas = get_origin_pro(annotation)

        param_meta: ParamMeta | None = None
        skip_param = False

        if metas:
            idx = 0
            while idx < len(metas):
                meta = metas[idx]
                if meta in (USE_FACTORY_MARK, IGNORE_PARAM_MARK):
                    skip_param = True
                    break
                if isinstance(meta, ParamMeta):
                    param_meta = param_meta.merge(meta) if param_meta else meta
                idx += 1

        if skip_param:
            return None

        alias = param.name
        if param_meta and param_meta.alias:
            alias = param_meta.alias

        param_type = base_type
        if param_meta and param_meta.constraint:
            param_type = Annotated[param_type, param_meta.constraint]

        schema, defs = json_schema(param_type)
        schema = _resolve_schema(schema, defs)
        if not schema:
            schema = {"type": "string"}

        schema = _attach_default(schema, default)

        return ToolParameter(
            name=param.name,
            alias=alias,
            schema=schema,
            required=not is_present(default),
            type_hint=param_type,
            default=default,
        )

    def _format_return(self, annotation: Any) -> str:
        if annotation is Signature.empty:
            return "None"
        if isinstance(annotation, type) and hasattr(annotation, "__name__"):
            return annotation.__name__
        return repr(annotation)

def _build_struct(
    func_name: str, parameters: Mapping[str, ToolParameter]
) -> type[Struct]:
    annotations: dict[str, Any] = {}
    namespace: dict[str, Any] = {}
    for name, param in parameters.items():
        annotation: Any = param.type_hint
        if is_present(param.default) and not is_json_compatible(param.default):
            annotation = annotation | type(None)
        annotations[name] = annotation
        field_kwargs: dict[str, Any] = {"name": param.alias}
        if is_present(param.default):
            default_val = param.default
            if isinstance(default_val, (list, dict, set, bytearray)):
                field_kwargs["default_factory"] = lambda dv=default_val: deepcopy(dv)
            else:
                field_kwargs["default"] = default_val
        namespace[name] = field(**field_kwargs)

    namespace["__annotations__"] = annotations
    struct_name = f"{func_name.capitalize()}ToolParams"
    return type(struct_name, (Struct,), namespace)


def _to_plain_json(value: Any) -> Any:
    if isinstance(value, Struct):
        return {k: _to_plain_json(v) for k, v in struct_asdict(value).items()}
    if PydanticBaseModel is not None and isinstance(value, PydanticBaseModel):
        return {k: _to_plain_json(v) for k, v in value.model_dump().items()}
    if isinstance(value, Mapping):
        return {k: _to_plain_json(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_to_plain_json(v) for v in value]
    if isinstance(value, list):
        return [_to_plain_json(v) for v in value]
    return value


def _decode_params(payload: bytes, signature: ToolSignature) -> Struct:
    raw = _JSON_DECODER.decode(payload)
    if not isinstance(raw, Mapping):  # pragma: no cover - defensive
        raise TypeError("Decoded tool payload must be a mapping")

    values: dict[str, Any] = {}
    for name, param in signature.parameters.items():
        if param.alias in raw:
            raw_value = raw[param.alias]
        elif name in raw:
            raw_value = raw[name]
        elif is_present(param.default):
            raw_value = _copy_default(param.default)
        else:
            continue
        values[name] = _coerce_value(raw_value, param)

    return signature.payload_struct(**values)


def _coerce_value(raw: Any, param: ToolParameter) -> Any:
    if raw is None:
        if is_present(param.default) and not is_json_compatible(param.default):
            return _copy_default(param.default)
        return None

    hint = param.type_hint

    if PydanticBaseModel is not None and isinstance(hint, type):
        try:
            is_pydantic_type = issubclass(hint, PydanticBaseModel)
        except TypeError:  # Generic aliases might raise TypeError
            is_pydantic_type = False
        if is_pydantic_type:
            if isinstance(raw, hint):
                return raw
            return hint.model_validate(raw)

    if isinstance(hint, type):
        try:
            is_struct_type = issubclass(hint, Struct)
        except TypeError:
            is_struct_type = False
        if is_struct_type:
            if isinstance(raw, hint):
                return raw

    try:
        return convert(raw, hint)
    except Exception:  # pragma: no cover - graceful fallback
        if isinstance(hint, type):
            try:
                if issubclass(hint, Struct) and isinstance(raw, Mapping):
                    return hint(**raw)
            except TypeError:
                pass
        return raw


def _copy_default(value: Any) -> Any:
    if isinstance(value, (list, dict, set, bytearray)):
        return deepcopy(value)
    return value


def _resolve_schema(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if not defs:
        return schema

    ref_prefix = "#/components/schemas/"

    def expand(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith(ref_prefix):
                schema_name = ref[len(ref_prefix) :]
                extras = {k: deepcopy(v) for k, v in node.items() if k != "$ref"}
                node.clear()
                node.update(deepcopy(defs.get(schema_name, {})))
                node.update(extras)
                expand(node)
                return
            for value in node.values():
                expand(value)
        elif isinstance(node, list):
            for item in node:
                expand(item)

    expand(schema)
    return schema


def _attach_default(schema: dict[str, Any], default: Maybe[Any]) -> dict[str, Any]:
    if not is_present(default):
        return schema

    if is_json_compatible(default):
        schema = deepcopy(schema)
        schema.setdefault("default", default)
    return schema
