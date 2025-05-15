from copy import deepcopy
from inspect import Parameter, signature
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    Callable,
    Mapping,
    TypeGuard,
    Union,
    cast,
    get_args,
    get_origin,
)
from warnings import warn

from ididi import DependentNode, Graph, INode, NodeConfig, Resolver
from ididi.config import USE_FACTORY_MARK
from ididi.utils.param_utils import MISSING as IDIDI_MISSING
from ididi.utils.typing_utils import is_builtin_type
from msgspec import Struct, convert
from msgspec.structs import fields as get_fields
from starlette.datastructures import FormData
from typing_extensions import TypeAliasType

from lihil.errors import NotSupportedError
from lihil.interface import MISSING as LIHIL_MISSING
from lihil.interface import IRequest, Maybe, ParamSource, R, T
from lihil.interface.marks import Struct
from lihil.interface.struct import IBodyDecoder, IDecoder, IFormDecoder, ITextualDecoder
from lihil.plugins.bus import EventBus
from lihil.utils.json import decoder_factory
from lihil.utils.string import find_path_keys, to_kebab_case
from lihil.utils.typing import get_origin_pro, is_nontextual_sequence, is_union_type
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
    ParsedParam,
    PathParam,
    QueryParam,
    RequestParam,
    StateParam,
)
from .returns import parse_returns
from .signature import EndpointSignature

STARLETTE_TYPES: tuple[type, ...] = (Request, WebSocket)
LIHIL_TYPES: tuple[type, ...] = (EventBus, Resolver)
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
            raise NotSupportedError(f"Not Supported type {annt}")
        return issubclass(annt, Struct) or is_file_body(annt)


def textdecoder_factory(
    param_type: type[T] | UnionType | GenericAlias,
) -> IDecoder[str | list[str], T]:
    if is_union_type(param_type):
        union_args = get_args(param_type)
        if bytes in union_args:
            raise NotSupportedError(
                "Union of bytes and other types is not supported, as it is always valid to decode the object as bytes"
            )
    else:
        if param_type is bytes:

            def str_to_bytes(content: str) -> bytes:
                return content.encode("utf-8")

            # here T is bytes
            return cast(IDecoder[str | list[str], T], str_to_bytes)

    def converter(content: str | list[str]) -> T:
        return convert(content, param_type, strict=False)

    return converter


def filedeocder_factory(filename: str):
    def file_decoder(form_data: FormData) -> UploadFile:
        if upload_file := form_data.get(filename):
            return cast(UploadFile, upload_file)
        raise FileNotFoundError(
            f"File {filename} not found in form data, please check the request"
        )

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


def formdecoder_factory(
    ptype: type[T] | UnionType,
) -> IDecoder[FormData, T] | IDecoder[bytes, T]:
    if not isinstance(ptype, type) or not issubclass(ptype, Struct):
        raise NotSupportedError(
            f"Only subclass of Struct is supported for `Form`, received {ptype}"
        )

    form_fields = get_fields(ptype)

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

        return convert(values, ptype)

    return form_decoder


def req_param_factory(
    name: str,
    alias: str,
    param_type: type[T] | UnionType,
    annotation: Any,
    default: Maybe[T],
    decoder: ITextualDecoder[T] | None = None,
    param_meta: ParamMeta | None = None,
    source: ParamSource = "query",
) -> "RequestParam[T]":

    if isinstance(param_meta, ParamMeta) and param_meta.constraint:
        param_type = cast(type[T], Annotated[param_type, param_meta.constraint])

    if decoder:
        decoder_ = decoder
    elif param_meta and param_meta.decoder is not None:
        decoder_ = cast(ITextualDecoder[T], param_meta.decoder)
    else:
        decoder_ = textdecoder_factory(param_type=param_type)

    if source == "path":
        req_param = PathParam(
            name=name,
            alias=alias,
            type_=param_type,
            annotation=annotation,
            decoder=cast(IDecoder[str, T], decoder_),
            default=default,
        )
    elif source == "header":
        return HeaderParam(
            name=name,
            alias=alias,
            type_=param_type,
            annotation=annotation,
            decoder=decoder_,
            default=default,
        )
    elif source == "cookie":
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

    else:
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
        elif param_origin and is_builtin_type(param_origin):
            return False
        else:
            return is_lhl_primitive(type(param_type))
    else:
        type_origin = get_origin(param_type) or param_type
        return param_type is IRequest or issubclass(type_origin, LIHIL_PRIMITIVES)


class EndpointParser:
    path_keys: tuple[str, ...]
    seen_path: set[str]

    def __init__(self, graph: Graph, route_path: str):
        self.graph = graph
        self.route_path = route_path
        self.path_keys = find_path_keys(route_path)
        self.seen_path = set(self.path_keys)
        self.node_derived = set[str]()

    def is_lhl_primitive(self, obj: Any):
        return is_lhl_primitive(obj)

    def _parse_node(
        self, node_type: INode[..., Any], node_config: NodeConfig | None = None
    ) -> list["ParsedParam[Any]"]:
        if node_config:
            node = self.graph.analyze(node_type, config=node_config)
        else:
            node = self.graph.analyze(node_type)

        params: list[Any | DependentNode] = [node]
        for dep_name, dep in node.dependencies.items():
            ptype, default = dep.param_type, dep.default_
            # TODO?: if param is Ignored then skip it for param analysis
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
            states: StateParam = StateParam(
                type_=type_, annotation=annotation, name=name, default=default
            )
            return states
        elif is_body_param(param_type):
            if param_meta and param_meta.decoder:
                decoder = cast(IBodyDecoder[T] | IFormDecoder[T], param_meta.decoder)
            else:
                decoder = None

            if is_file_body(param_type):
                body_param = file_body_param(
                    name,
                    param_type,
                    annotation=annotation,
                    default=default,
                    meta=None,
                )
                return cast(FormParam[T], body_param)

            if decoder is None:
                decoder = decoder_factory(param_type)

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

        if param_meta.extra and param_meta.extra.use_jwt:
            from lihil.auth.jwt import jwt_decoder_factory

            decoder = jwt_decoder_factory(payload_type=type_)
        else:
            decoder = None

        req_param = req_param_factory(
            name=name,
            alias=header_key,
            param_type=type_,
            annotation=annotation,
            decoder=decoder,
            source="header",
            default=default,
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
        location = "header"
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
            source=location,
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

    def _parse_declared(
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMeta,
    ) -> "ParsedParam[T] | list[ParsedParam[T]]":
        assert param_meta.source
        param_source = param_meta.source
        param_alias = param_meta.alias or name

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
    ) -> list["ParsedParam[T]"]:
        parsed_type, pmetas = get_origin_pro(annotation)
        parsed_type = cast(type[T], parsed_type)
        param_meta: ParamMeta | None = None
        if pmetas:
            for idx, meta in enumerate(pmetas):
                if isinstance(meta, (ParamMeta, BodyMeta)):
                    param_meta = meta
                elif meta == USE_FACTORY_MARK:
                    factory, config = pmetas[idx + 1], pmetas[idx + 2]
                    return self._parse_node(factory, config)

        if param_meta is None or not param_meta.source:
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

    def parse_params(
        self,
        func_params: Mapping[str, Parameter],
        path_keys: tuple[str, ...] | None = None,
    ) -> EndpointParams:
        if path_keys:
            self.path_keys += path_keys

        params: ParamMap[RequestParam[Any]] = {}
        bodies: ParamMap[BodyParam[Any, Any]] = {}
        nodes: ParamMap[DependentNode] = {}
        states: ParamMap[StateParam] = {}

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
                elif isinstance(req_param, StateParam):
                    states[req_param.name] = req_param
                else:
                    params[req_param.name] = req_param

        if self.seen_path:
            warn(f"Unused path keys {self.seen_path}")

        ep_params = EndpointParams(
            params=params, bodies=bodies, nodes=nodes, states=states
        )
        return ep_params

    def parse(self, f: Callable[..., R]) -> EndpointSignature[R]:
        func_sig = signature(f)

        params = self.parse_params(func_sig.parameters)
        retns = parse_returns(func_sig.return_annotation)

        status, retparam = next(iter(retns.items()))
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
            states=params.states,
            dependencies=params.nodes,
            transitive_params=transitive_params,
            return_params=retns,
            status_code=status,
            return_encoder=retparam.encoder,
            scoped=scoped,
            form_meta=form_meta,
        )
        return ep_sig
