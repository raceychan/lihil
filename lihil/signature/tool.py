from copy import deepcopy
from inspect import Parameter, Signature, signature
from types import UnionType
from typing import Annotated, Any, Callable, TypedDict

from ididi.config import IGNORE_PARAM_MARK, USE_FACTORY_MARK
from typing_extensions import NotRequired

from lihil.errors import InvalidParamError, NotSupportedError
from lihil.interface import MISSING, Maybe, Record, is_present
from lihil.utils.json import is_json_compatible, json_schema
from lihil.utils.typing import get_origin_pro

from .params import ParamMeta


class ToolParameter(Record):
    name: str
    alias: str
    schema: dict[str, Any]
    required: bool
    type_hint: type[Any] | UnionType
    default: Maybe[Any] = MISSING


class ToolSchema(TypedDict):
    type: str
    name: str
    description: NotRequired[str]
    parameters: dict[str, Any]


class ToolSignature(Record):
    name: str
    description: str
    parameters: dict[str, ToolParameter]
    return_type: str

    @property
    def schema(self) -> ToolSchema:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in self.parameters.values():
            properties[param.alias] = param.schema
            if param.required:
                required.append(param.alias)

        parameters: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            parameters["required"] = required

        schema_dict: ToolSchema = {
            "type": "function",
            "name": self.name,
            "parameters": parameters,
        }
        if self.description:
            schema_dict["description"] = self.description
        return schema_dict


def _resolve_schema(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if not defs:
        return schema

    ref_prefix = "#/components/schemas/"

    def expand(node: dict[str, Any] | list[Any] | str) -> None:
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
        else:
            pass  # node is str

    expand(schema)
    return schema


def _attach_default(schema: dict[str, Any], default: Maybe[Any]) -> dict[str, Any]:
    if not is_present(default):
        return schema

    if is_json_compatible(default):
        schema = deepcopy(schema)
        schema.setdefault("default", default)
    return schema


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
        return ToolSignature(
            name=func.__name__,
            description=description,
            parameters=parameters,
            return_type=self._format_return(func_sig.return_annotation),
        )

    def _parse_param(self, param: Parameter) -> ToolParameter | None:
        default: Maybe[Any]
        if param.default is Parameter.empty:
            default = MISSING
        else:
            default = param.default

        annotation = (
            param.annotation if param.annotation is not Parameter.empty else MISSING
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
