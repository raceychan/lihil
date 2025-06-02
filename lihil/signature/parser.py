from copy import deepcopy
from dataclasses import MISSING as DS_MISSING
from dataclasses import fields as get_dc_fields
from dataclasses import is_dataclass
from inspect import Parameter, signature
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    Callable,
    Literal,
    Mapping,
    TypeGuard,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
from warnings import warn

from ididi import DependentNode, Graph, INode, NodeConfig, Resolver
from ididi.config import USE_FACTORY_MARK
from ididi.utils.param_utils import MISSING as IDIDI_MISSING
from msgspec import Struct, convert
from msgspec.structs import NODEFAULT, FieldInfo
from msgspec.structs import fields as get_fields
from starlette.datastructures import FormData
from typing_extensions import NotRequired, TypeAliasType, is_typeddict

from lihil.errors import InvalidParamError, InvalidParamPackError
from lihil.interface import MISSING as LIHIL_MISSING
from lihil.interface import IRequest, Maybe, R, T, is_provided
from lihil.interface.marks import Struct
from lihil.interface.struct import IBodyDecoder, IDecoder, IFormDecoder, ITextualDecoder
from lihil.utils.json import decoder_factory
from lihil.utils.string import find_path_keys, to_kebab_case
from lihil.utils.typing import (
    get_origin_pro,
    is_nontextual_sequence,
    is_structured_type,
    is_union_type,
    lenient_issubclass,
)
from lihil.vendors import Request, UploadFile, WebSocket

from .params import (
    BodyMeta,
    BodyParam,
    CookieParam,
    EndpointParams,
    FormMeta,
    FormParam,
    HeaderParam,
    ParamMap,
    ParamMeta,
    ParamSource,
    ParsedParam,
    PathParam,
    PluginParam,
    QueryParam,
    RequestParam,
)
from .returns import parse_returns
from .signature import EndpointSignature

STARLETTE_TYPES: tuple[type, ...] = (Request, WebSocket)
LIHIL_TYPES: tuple[type, ...] = (Resolver,)
LIHIL_PRIMITIVES: tuple[type, ...] = STARLETTE_TYPES + LIHIL_TYPES


def is_file_body(annt: Any) -> TypeGuard[type[UploadFile]]:
    annt_origin = get_origin(annt) or annt
    return annt_origin is UploadFile


def is_body_param(annt: Any) -> bool:
    if is_union_type(annt):
        return any(is_body_param(arg) for arg in get_args(annt))
    else:
        # issubclass does not work with GenericAlias, e.g. dict[str, str], in python 3.13. so we check its origin
        if annt_origin := get_origin(annt):
            return is_body_param(annt_origin)
        if not isinstance(annt, type):
            raise InvalidParamError(f"Invalid type {annt} for body param")
        return is_structured_type(annt) or is_file_body(annt)


def textdecoder_factory(
    param_type: type[T] | UnionType | GenericAlias,
) -> ITextualDecoder[T]:
    if is_union_type(param_type):
        union_args = get_args(param_type)
        if bytes in union_args:
            raise InvalidParamError(
                "Union of bytes and other types is not supported, as it is always valid to decode the object as bytes"
            )
    if param_type is bytes:

        def str_to_bytes(content: str) -> bytes:
            return content.encode("utf-8")

        return str_to_bytes  # type: ignore[no-untyped-def]

    if param_type is str:

        def dummy(content: str):
            return content

        return dummy  # type: ignore[no-untyped-def]

    def converter(content: str | list[str]) -> T:
        return convert(content, param_type, strict=False)

    return converter


def filedeocder_factory(filename: str):
    def file_decoder(form_data: FormData) -> UploadFile:
        file = form_data[filename]
        return cast(UploadFile, file)

    return file_decoder


def file_body_param(
    name: str,
    type_: type[UploadFile],
    annotation: Any,
    default: Any,
    meta: FormMeta | None = None,
) -> "FormParam[UploadFile]":
    if meta and meta.decoder:
        decoder_ = meta.decoder
    else:
        decoder_ = filedeocder_factory(name)
    if meta is None:
        meta = FormMeta()
    req_param = FormParam[UploadFile](
        name=name,
        alias=name,
        type_=type_,
        annotation=annotation,
        decoder=decoder_,
        default=default,
        meta=meta,
    )
    return req_param


def lexient_get_fields(ptype: type[Any]):
    # msgspec.Struct
    if lenient_issubclass(ptype, Struct):
        return tuple(get_fields(ptype))
    # dataclass
    elif is_dataclass(ptype):
        result: list[FieldInfo] = []
        for f in get_dc_fields(ptype):
            default = NODEFAULT if f.default is DS_MISSING else f.default
            default_factory = (
                NODEFAULT if f.default_factory is DS_MISSING else f.default_factory
            )
            result.append(
                FieldInfo(
                    name=f.name,
                    type=f.type,
                    default=default,
                    default_factory=default_factory,
                    encode_name=f.name,
                )
            )
        return tuple(result)
    # TypedDict
    elif is_typeddict(ptype):
        hints = get_type_hints(ptype)
        optionals = getattr(ptype, "__optional_keys__", set[str]())

        result = []
        for name, typ in hints.items():
            if name in optionals:
                typ = Union[(ptype, None)]
                default = None
            else:
                default = NODEFAULT
            result.append(
                FieldInfo(
                    name=name,
                    type=typ,
                    default=default,
                    encode_name=name,
                )
            )
        return tuple(result)
    else:
        raise TypeError(f"Unsupported type: {ptype}")


def formdecoder_factory(
    ptype: type[T] | UnionType,
) -> IDecoder[FormData, T] | IDecoder[bytes, T]:
    if not is_structured_type(ptype, homogeneous_union=True):
        raise InvalidParamError(f"Form type must be a structured type")

    if get_origin(ptype) is UnionType:
        raise InvalidParamError(f"Union of multiple form type is not supported yet")

    ptype = cast(type[T], ptype)
    form_fields = lexient_get_fields(ptype)

    def form_decoder(form_data: FormData) -> T:
        values = {}
        for ffield in form_fields:
            if is_nontextual_sequence(ffield.type):
                val = form_data.getlist(ffield.encode_name)
            else:
                val = form_data.get(ffield.encode_name)

            if val is None:
                if ffield.required:  # has not default
                    continue  # let msgspec `convert` raise error
                val = deepcopy(ffield.default)

            values[ffield.name] = val

        return convert(values, ptype)  # type: ignore[no-untyped-call]

    return form_decoder


def req_param_factory(
    name: str,
    alias: str,
    param_type: type[T] | UnionType,
    annotation: Any,
    default: Maybe[T],
    decoder: ITextualDecoder[T] | None = None,
    param_meta: ParamMeta | None = None,
    source: Literal["path", "query", "header", "cookie"] = "query",
) -> "RequestParam[T]":

    if source in ("path", "query") and is_structured_type(param_type):
        raise InvalidParamError(
            f"Structured type, or a union that contains a structured type is not supported for {source} param, received: {param_type}"
        )

    if isinstance(param_meta, ParamMeta) and param_meta.constraint:
        param_type = cast(type[T], Annotated[param_type, param_meta.constraint])

    if decoder:
        decoder_ = decoder
    elif param_meta and param_meta.decoder is not None:
        decoder_ = cast(ITextualDecoder[T], param_meta.decoder)
    else:
        decoder_ = textdecoder_factory(param_type=param_type)

    match source:
        case "path":
            req_param = PathParam(
                name=name,
                alias=alias,
                type_=param_type,
                annotation=annotation,
                decoder=cast(IDecoder[str, T], decoder_),
                default=default,
            )
        case "header":
            return HeaderParam(
                name=name,
                alias=alias,
                type_=param_type,
                annotation=annotation,
                decoder=decoder_,
                default=default,
            )
        case "cookie":
            assert param_meta
            cookie_name = param_meta.alias or to_kebab_case(name)
            return CookieParam(
                name=name,
                cookie_name=cookie_name,
                alias=alias,
                type_=param_type,
                annotation=annotation,
                decoder=decoder_,
                default=default,
            )
        case "query":
            req_param = QueryParam(
                name=name,
                alias=alias,
                type_=param_type,
                annotation=annotation,
                decoder=decoder_,
                default=default,
            )

    return req_param


def is_lhl_primitive(param_type: Any) -> TypeGuard[type]:
    "Dependencies that should be injected and managed by lihil"
    if not isinstance(param_type, type):
        param_origin = get_origin(param_type)
        if param_origin is Union:
            return any(is_lhl_primitive(arg) for arg in get_args(param_type))
        else:
            return is_lhl_primitive(type(param_type))
    else:
        type_origin = get_origin(param_type) or param_type
        return param_type is IRequest or lenient_issubclass(
            type_origin, LIHIL_PRIMITIVES
        )


class EndpointParser:
    path_keys: tuple[str, ...]
    seen_path: set[str]

    def __init__(self, graph: Graph, route_path: str):
        self.graph = graph
        self.route_path = route_path
        self.path_keys = find_path_keys(route_path)
        self.seen_path = set(self.path_keys)
        self.node_derived = set[str]()

    def _parse_node(
        self, node_type: INode[..., Any], node_config: NodeConfig | None = None
    ) -> list["ParsedParam[Any]"]:
        if node_config:
            node = self.graph.analyze(node_type, config=node_config)
        else:
            node = self.graph.analyze(node_type)

        ignores = node_config.ignore if node_config else ()

        params: list[Any | DependentNode] = [node]
        for dep_name, dep in node.dependencies.items():
            ptype, default = dep.param_type, dep.default_
            if dep_name in ignores or ptype in ignores:
                continue
            default = LIHIL_MISSING if default is IDIDI_MISSING else default
            sub_params = self.parse_param(dep_name, cast(type, ptype), default)
            for sp in sub_params:
                if not isinstance(sp, DependentNode):
                    self.node_derived.add(sp.name)
            params.extend(sub_params)
        return params

    def _parse_rule_based(
        self,
        name: str,
        param_type: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMeta | None = None,
    ) -> "ParsedParam[T] | list[ParsedParam[T]]":
        if name in self.path_keys:  # simplest case
            self.seen_path.discard(name)
            req_param = req_param_factory(
                name=name,
                alias=name,
                param_type=param_type,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
                source="path",
            )
        elif is_lhl_primitive(param_type):
            type_ = Request if param_type is IRequest else param_type
            plugins: PluginParam = PluginParam(
                type_=type_, annotation=annotation, name=name, default=default
            )
            return plugins
        elif is_body_param(param_type):
            if param_meta and param_meta.decoder:
                decoder = cast(IBodyDecoder[T] | IFormDecoder[T], param_meta.decoder)
            else:
                decoder = decoder_factory(param_type)

            if is_file_body(param_type):
                body_param = file_body_param(
                    name,
                    param_type,
                    annotation=annotation,
                    default=default,
                    meta=None,
                )
                return cast(FormParam[T], body_param)

            req_param = BodyParam(
                name=name,
                alias=name,
                annotation=annotation,
                type_=param_type,
                default=default,
                decoder=cast(IBodyDecoder[T], decoder),
            )
        elif param_type in self.graph.nodes:
            nodes = self._parse_node(param_type)
            return nodes
        else:  # default case
            req_param = req_param_factory(
                name=name,
                alias=name,
                param_type=param_type,
                annotation=annotation,
                param_meta=param_meta,
                source="query",
                default=default,
            )
        return req_param

    def _parse_auth_header(
        self,
        name: str,
        header_key: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMeta,
    ) -> "ParsedParam[T]":

        req_param = req_param_factory(
            name=name,
            alias=header_key,
            param_type=type_,
            default=default,
            annotation=annotation,
            param_meta=param_meta,
            source="header",
        )

        return req_param

    def _parse_header(
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMeta,
    ) -> "ParsedParam[T]":
        header_key = param_meta.alias or to_kebab_case(name)

        if header_key.lower() == "authorization":
            return self._parse_auth_header(
                name=name,
                header_key=header_key,
                type_=type_,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )

        return req_param_factory(
            name=name,
            alias=header_key,
            param_type=type_,
            annotation=annotation,
            source="header",
            default=default,
            param_meta=param_meta,
        )

    def _parse_body(
        self,
        name: str,
        param_alias: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMeta,
    ) -> BodyParam[bytes, T] | FormParam[T]:
        if isinstance(param_meta, FormMeta):
            if type_ is UploadFile:
                body_param = file_body_param(
                    name=name,
                    type_=type_,
                    annotation=annotation,
                    default=default,
                    meta=param_meta,
                )
                return cast(FormParam[T], body_param)

            content_type = param_meta.content_type or "multipart/form-data"
            decoder = param_meta.decoder or formdecoder_factory(type_)
            body_param = FormParam(
                name=name,
                alias=param_alias,
                type_=type_,
                annotation=annotation,
                default=default,
                decoder=cast(IFormDecoder[T], decoder),
                content_type=content_type,
                meta=param_meta,
            )
        else:
            decoder_ = param_meta.decoder or decoder_factory(type_)
            body_param = BodyParam[bytes, T](
                name=name,
                alias=param_alias,
                type_=type_,
                annotation=annotation,
                default=default,
                decoder=cast(IBodyDecoder[T], decoder_),
            )
        return body_param

    def _parse_param_pack(
        self,
        name: str,
        type_: type | UnionType,
        annotation: Any,
        default: Any,
        param_meta: ParamMeta,
    ) -> list[ParsedParam[Any]]:
        if is_union_type(type_):
            raise InvalidParamPackError(
                f"param pack {name}: {annotation} should not be a union type"
            )

        type_ = cast(type[Any], type_)

        if is_provided(default):
            raise InvalidParamPackError(
                f"param pack {name}: {annotation} should not have a default value"
            )

        params: list[ParsedParam[Any]] = []

        if is_typeddict(type_):
            for name, annt in type_.__annotations__.items():
                origin = get_origin(annt)
                if origin is NotRequired:
                    not_required_type = get_args(annt)[0]
                    annt = Union[(not_required_type, None)]
                    fdefault = None
                else:
                    fdefault = LIHIL_MISSING

                fparams = self.parse_param(
                    name=name,
                    annotation=annt,
                    default=fdefault,
                    source=param_meta.source,
                )
                params.extend(fparams)
        elif lenient_issubclass(type_, Struct):
            for f in get_fields(type_):
                fdefault = f.default if f.default is not NODEFAULT else LIHIL_MISSING
                if f.default_factory is not NODEFAULT:
                    raise InvalidParamPackError(
                        f"Param {f.name} with default factory is not supported in param pack"
                    )
                fparams = self.parse_param(
                    name=f.name,
                    annotation=f.type,
                    default=fdefault,
                    source=param_meta.source,
                )
                params.extend(fparams)
        elif is_dataclass(type_):  # type: ignore
            for name, f in type_.__dataclass_fields__.items():
                fdefault = LIHIL_MISSING if f.default is DS_MISSING else f.default
                if f.default_factory is not DS_MISSING:
                    raise InvalidParamPackError(
                        f"Param {f.name!r} has default factory, which is not supported in param pack"
                    )
                fparams = self.parse_param(
                    name=f.name,
                    annotation=f.type,  # type: ignore
                    default=fdefault,
                    source=param_meta.source,
                )
                params.extend(fparams)
        else:
            raise InvalidParamPackError(f"Invalid type for param pack {type_}")

        return params

    def _parse_declared(
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMeta,
    ) -> ParsedParam[T] | list[ParsedParam[T]]:
        assert param_meta.source
        param_source = param_meta.source
        param_alias = param_meta.alias or name

        skip_unpack = param_meta.extra_meta.get("skip_unpack", False)

        if param_source in ("path", "query", "header", "cookie"):
            if not skip_unpack and is_structured_type(type_):
                return self._parse_param_pack(
                    name=name,
                    type_=type_,
                    annotation=annotation,
                    default=default,
                    param_meta=param_meta,
                )

        if param_source == "header":
            return self._parse_header(
                name=name,
                type_=type_,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )
        elif param_source == "body":
            return self._parse_body(
                name,
                param_alias=param_alias,
                type_=type_,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )
        elif param_source == "plugin":
            type_ = type_ or type_
            return PluginParam(
                type_=type_, annotation=annotation, name=name, default=default
            )

        req_param = req_param_factory(
            name=name,
            alias=param_alias,
            param_type=type_,
            annotation=annotation,
            source=param_source,
            default=default,
            param_meta=param_meta,
        )
        return req_param

    def parse_param(
        self,
        name: str,
        annotation: type[T] | UnionType | GenericAlias | TypeAliasType,
        default: Maybe[T] = LIHIL_MISSING,
        source: ParamSource | None = None,
    ) -> list[ParsedParam[T]]:
        parsed_type, parsed_metas = get_origin_pro(annotation)
        parsed_type = cast(type[T], parsed_type)
        param_meta: ParamMeta | None = None
        if parsed_metas:
            for idx, meta in enumerate(parsed_metas):
                if isinstance(meta, (ParamMeta, BodyMeta)):
                    if param_meta:
                        param_meta = param_meta.merge(meta)  # type: ignore
                    else:
                        param_meta = meta
                elif meta == USE_FACTORY_MARK:
                    factory, config = parsed_metas[idx + 1], parsed_metas[idx + 2]
                    return self._parse_node(factory, config)

        if source is not None:
            if param_meta is None:
                param_meta = ParamMeta(source=source)
            elif param_meta.source is None:
                param_meta = param_meta.replace(source=source)

        if param_meta is None or param_meta.source is None:
            res = self._parse_rule_based(
                name=name,
                param_type=parsed_type,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )
        else:
            res = self._parse_declared(
                name=name,
                type_=parsed_type,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )
        return res if isinstance(res, list) else [res]

    def parse_params(self, func_params: Mapping[str, Parameter]) -> EndpointParams:
        params: ParamMap[RequestParam[Any]] = {}
        bodies: ParamMap[BodyParam[Any, Any]] = {}
        nodes: ParamMap[DependentNode] = {}
        plugins: ParamMap[PluginParam] = {}

        for name, param in func_params.items():
            annotation, default = param.annotation, param.default
            if param.default is Parameter.empty:
                default = LIHIL_MISSING
            else:
                default = param.default
            parsed_params = self.parse_param(name, annotation, default)
            for req_param in parsed_params:
                if isinstance(req_param, DependentNode):
                    if name in nodes:  # only keep the top dependency as param
                        continue
                    nodes[name] = req_param
                elif isinstance(req_param, BodyParam):
                    bodies[req_param.name] = req_param
                elif isinstance(req_param, PluginParam):
                    plugins[req_param.name] = req_param
                else:
                    params[req_param.name] = req_param

        if self.seen_path:
            warn(f"Unused path keys {self.seen_path}")

        ep_params = EndpointParams(
            params=params, bodies=bodies, nodes=nodes, plugins=plugins
        )
        return ep_params

    def parse(self, f: Callable[..., R]) -> EndpointSignature[R]:
        func_sig = signature(f)

        params = self.parse_params(func_sig.parameters)
        retns = parse_returns(func_sig.return_annotation)

        scoped = any(
            self.graph.should_be_scoped(node.dependent)
            for node in params.nodes.values()
        )
        body_param_pair = params.get_body()
        body_param = body_param_pair[1] if body_param_pair else None

        form_meta = None
        if body_param and isinstance(body_param, FormParam):
            form_meta = body_param.meta

        transitive_params: set[str] = {
            p for p in self.node_derived if p not in func_sig.parameters
        }

        ep_sig = EndpointSignature(
            route_path=self.route_path,
            header_params=params.get_source("header"),
            query_params=params.get_source("query"),
            path_params=params.get_source("path"),
            body_param=body_param_pair,
            plugins=params.plugins,
            dependencies=params.nodes,
            transitive_params=transitive_params,
            return_params=retns,
            scoped=scoped,
            form_meta=form_meta,
        )
        return ep_sig
