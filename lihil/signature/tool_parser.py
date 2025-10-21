from copy import deepcopy
from inspect import Parameter, Signature, signature
from types import UnionType
from typing import Annotated, Any, Callable, Generic, TypedDict

from ididi.config import IGNORE_PARAM_MARK, USE_FACTORY_MARK
from msgspec.json import encode as msg_encode
from typing_extensions import NotRequired, TypedDict

from lihil.errors import InvalidParamError, NotSupportedError
from lihil.interface import MISSING, Maybe, P, R, Record, is_present
from lihil.utils.json import decoder_factory, is_json_compatible, json_schema
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
    parameters: dict[str, ToolParameter]
    return_type: Maybe[type]
    virtual_dict: type[dict[str, Any]]
    decoder: Callable[[bytes], dict[str, Any]]

    @property
    def param_schema(self) -> dict[str, str]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in self.parameters.values():
            properties[param.alias] = param.schema
            if param.required:
                required.append(param.alias)

        parameters: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            parameters["required"] = required

        return parameters


class Tool(Record, Generic[P, R]):
    """
    params = tool.decode_params(data: bytes)
    await graph.resolve(tool, **params) -> bytes
    """

    name: str
    description: str
    signature: ToolSignature
    func: Callable[P, R]

    @property
    def schema(self) -> ToolSchema:
        params = self.signature.param_schema

        schema_dict: ToolSchema = {
            "type": "function",
            "name": self.name,
            "parameters": params,
        }
        if self.description:
            schema_dict["description"] = self.description
        return schema_dict

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.func(*args, **kwargs)

    def decode_params(self, data: bytes) -> dict[str, Any]:
        payload = self.signature.decoder(data)
        for param in self.signature.parameters.values():
            alias = param.alias
            if alias not in payload and is_present(param.default):
                payload[alias] = param.default
        return payload

    def encode_return(self, value: R) -> bytes:
        return msg_encode(value)


def _build_virtual_dict(
    func_name: str,
    module: str,
    parameters: dict[str, ToolParameter],
) -> type[dict[str, Any]]:
    annotations: dict[str, Any] = {}
    for param in parameters.values():
        key = param.alias
        field_type = param.type_hint
        if not param.required:
            field_type = NotRequired[field_type]  # type: ignore[assignment]
        annotations[key] = field_type

    typed_dict = TypedDict(f"{func_name}_params", annotations)
    typed_dict.__module__ = module
    return typed_dict


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


def _parse_param(param: Parameter) -> ToolParameter | None:
    default: Maybe[Any]
    if param.default is Parameter.empty:
        default = MISSING
    else:
        default = param.default

    if param.annotation is Parameter.empty:
        raise InvalidParamError(f"Parameter {param.name!r} is missing type annotation")

    annotation = param.annotation
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


def tool(func: Callable[P, R]) -> Tool[P, R]:
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
        parsed = _parse_param(param)
        if parsed is None:
            continue
        if parsed.alias in seen_aliases:
            raise InvalidParamError(
                f"Duplicated parameter alias detected: {parsed.alias!r}"
            )
        seen_aliases.add(parsed.alias)
        parameters[parsed.name] = parsed

    description = func.__doc__.strip() if func.__doc__ else ""
    return_type = (
        func_sig.return_annotation
        if func_sig.return_annotation is not Signature.empty
        else MISSING
    )

    virtual_dict = _build_virtual_dict(
        func.__name__,
        func.__module__,
        parameters,
    )
    sig = ToolSignature(
        parameters=parameters,
        return_type=return_type,
        virtual_dict=virtual_dict,
        decoder=decoder_factory(virtual_dict),
    )

    return Tool(
        name=func.__name__,
        description=description,
        signature=sig,
        func=func,
    )


"""
class ToolRegistry:
    tools: dict[str, ToolSignature] = {}

    def register(self, func: Callable[..., Any]) -> None:
        self.tools[sig.name] = parse(func)
"""
