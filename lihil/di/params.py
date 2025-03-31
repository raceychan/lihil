from copy import deepcopy
from inspect import Parameter
from types import GenericAlias, UnionType
from typing import (
    Any,
    Protocol,
    Sequence,
    TypeAliasType,
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
from msgspec import convert, field
from msgspec.structs import fields as get_fields
from starlette.datastructures import FormData

from lihil.errors import NotSupportedError
from lihil.interface import (
    MISSING,
    BodyContentType,
    CustomDecoder,
    Maybe,
    ParamLocation,
)
from lihil.interface.marks import ParamMarkType, Struct, extra_mark_type
from lihil.interface.struct import Base, IDecoder, IFormDecoder, ITextDecoder
from lihil.plugins.bus import EventBus
from lihil.utils.parse import parse_header_key
from lihil.utils.phasing import build_union_decoder, decoder_factory, to_bytes, to_str
from lihil.utils.typing import get_origin_pro, is_nontextual_sequence, is_union_type
from lihil.vendor_types import FormData, Request, UploadFile

type ParsedParam[T] = RequestParam[T] | RequestBodyParam[T] | PluginParam[
    T
] | DependentNode


LIHIL_DEPENDENCIES: tuple[type, ...] = (Request, EventBus, Resolver)


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


def txtdecoder_factory(
    t: type | UnionType | GenericAlias,
) -> IDecoder[Any]:
    if is_union_type(t):
        union_args = get_args(t)
        if str in union_args:
            return build_union_decoder(union_args, str)
        if bytes in union_args:
            return build_union_decoder(union_args, bytes)
        else:
            return decoder_factory(t)

    if t is str:
        return to_str
    elif t is bytes:
        return to_bytes
    return decoder_factory(t)


def filedeocder_factory(filename: str):
    def file_decoder(form_data: FormData) -> UploadFile | None:
        if upload_file := form_data.get(filename):
            return cast(UploadFile, upload_file)

    return file_decoder


def file_body_param(
    name: str, type_: type[UploadFile], annotation: Any, default: Any
) -> "RequestBodyParam[Any]":
    decoder = filedeocder_factory(name)
    content_type = "multipart/form-data"
    req_param = RequestBodyParam(
        name=name,
        alias=name,
        type_=type_,
        annotation=annotation,
        decoder=decoder,
        default=default,
        content_type=content_type,
    )
    return req_param


def formdecoder_factory[T](ptype: type[T] | UnionType):
    if not isinstance(ptype, type) or not issubclass(ptype, Struct):
        if ptype is bytes:
            return to_bytes

        raise NotSupportedError(
            f"currently only bytes or subclass of Struct is supported for `Form`, received {ptype}"
        )

    form_fields = get_fields(ptype)

    def form_decoder(form_data: FormData) -> T:
        values = {}
        for ffield in form_fields:
            if is_nontextual_sequence(ffield.type):
                val = form_data.getlist(ffield.encode_name)
            else:
                val = form_data.get(ffield.encode_name)

            if not val:
                if ffield.required:  # has not diffult
                    continue  # let msgspec `convert` raise error
                val = deepcopy(ffield.default)

            values[ffield.name] = val

        return convert(values, ptype)

    return form_decoder


class RequestParamBase[T](Base):
    name: str
    alias: str
    type_: type[T] | UnionType | GenericAlias
    annotation: Any
    location: ParamLocation
    default: Maybe[Any] = MISSING
    required: bool = False

    @property
    def type_repr(self) -> str:
        ty_origin = getattr(self.type_, "__origin__", None)
        if ty_origin is Union:
            type_repr = repr(self.type_).lstrip("typing.")
        else:
            type_repr = getattr(self.type_, "__name__", repr(self.type_))
        return type_repr

    def __post_init__(self):
        self.required = self.default is MISSING


class RequestParam[T](RequestParamBase[T], kw_only=True):
    decoder: ITextDecoder[T]

    def __repr__(self) -> str:
        return f"RequestParam<{self.location}>({self.name}: {self.type_repr})"

    def decode(self, content: str) -> T:
        return self.decoder(content)


class RequestBodyParam[T](RequestParamBase[T], kw_only=True):
    location: ParamLocation = "body"
    decoder: IDecoder[T] | IFormDecoder[T]
    content_type: BodyContentType = "application/json"

    def __post_init__(self):
        assert self.location == "body"

    def __repr__(self) -> str:
        return f"RequestBodyParam<{self.content_type}>({self.name}: {self.type_repr})"

    def decode(self, content: bytes | FormData) -> T:
        return self.decoder(content)  # type: ignore


class PluginParam[T](Base):
    type_: type[T]
    name: str
    default: Maybe[Any] = MISSING
    required: bool = False
    loader: "PluginLoader[T] | None" = None

    def __post_init__(self):
        self.required = self.default is MISSING


# PluginProvider[T]
#  parse -> PluginParam[T]
#  load -> T


class PluginLoader[T](Protocol):
    def __call__(self, request: Request, resolver: Resolver) -> T: ...


class PluginProvider[T](Protocol):
    load: PluginLoader[T]

    def parse(
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: "ParamMetas",
    ) -> list[PluginParam[T]]: ...


class ParamMetas(Base):
    custom_decoder: CustomDecoder | None
    mark_type: ParamMarkType | None
    metas: tuple[Any, ...]
    factory: INode[..., Any] | None = None
    config: NodeConfig | None = None

    @classmethod
    def from_metas(cls, metas: list[Any]) -> "ParamMetas":
        current_mark_type = None
        decoder = None
        factory = None
        config = None

        for idx, meta in enumerate(metas):
            if isinstance(meta, CustomDecoder):
                decoder = meta
            elif mark_type := extra_mark_type(meta):
                if current_mark_type and mark_type is not current_mark_type:
                    raise NotSupportedError("can't use more than one param mark")
                elif mark_type == "header":
                    header_key = metas[idx - 1]
                    if not isinstance(header_key, str):
                        metas[idx - 1] = None
                current_mark_type = mark_type
            elif meta == USE_FACTORY_MARK:  # TODO: use PluginParser
                factory, config = metas[idx + 1], metas[idx + 2]

        return ParamMetas(
            custom_decoder=decoder,
            mark_type=current_mark_type,
            metas=tuple(metas),
            factory=factory,
            config=config,
        )


class EndpointParams(Base):
    params: dict[str, RequestParam[Any]] = field(default_factory=dict)
    bodies: dict[str, RequestBodyParam[Any]] = field(default_factory=dict)
    nodes: dict[str, DependentNode] = field(default_factory=dict)
    plugins: dict[str, PluginParam[Any]] = field(default_factory=dict)

    def get_location(self, location: ParamLocation) -> dict[str, RequestParam[Any]]:
        return {n: p for n, p in self.params.items() if p.location == location}

    def get_body(self) -> tuple[str, RequestBodyParam[Any]] | None:
        if not self.bodies:
            body_param = None
        elif len(self.bodies) == 1:
            body_param = next(iter(self.bodies.items()))
        else:
            # "use defstruct to dynamically define a type"
            raise NotSupportedError(
                "Endpoint with multiple body params is not yet supported"
            )
        return body_param


class ParamParser:
    path_keys: tuple[str, ...]
    seen: set[str]

    def __init__(self, graph: Graph, path_keys: tuple[str, ...] | None = None):
        self.graph = graph

        if path_keys:
            self.path_keys = path_keys
            self.seen = set(self.path_keys)
        else:
            self.path_keys = ()
            self.seen = set()

        # mark_type or param_type, dict[str | type, PluginProvider]
        self.plugin_provider: dict[str, PluginProvider[Any]] = {}
        self.plugin_types = LIHIL_DEPENDENCIES

    def register_provider(
        self, mark: TypeAliasType | GenericAlias, provider: PluginProvider[Any]
    ) -> None:
        _, metas = get_origin_pro(mark)

        if not metas:
            raise NotSupportedError("Invalid mark type")

        for meta in metas:
            if mark_type := extra_mark_type(meta):
                break
        else:
            raise NotImplementedError("Invalid mark type")

        self.plugin_provider[mark_type] = provider

    def is_plugin_type(self, param_type: Any) -> TypeGuard[type]:
        "Dependencies that should be injected and managed by lihil"
        if not isinstance(param_type, type):
            param_origin = get_origin(param_type)
            if param_origin is Union:
                return any(self.is_plugin_type(arg) for arg in get_args(param_type))
            elif is_builtin_type(param_origin):
                return False
            else:
                raise RuntimeError("get_origin_pro should prevent this")
        return issubclass(param_type, self.plugin_types)

    def _parse_rule_based[T](
        self,
        name: str,
        param_type: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMetas | None = None,
    ) -> ParsedParam[T] | list[ParsedParam[T]]:
        if name in self.path_keys:  # simplest case
            self.seen.discard(name)
            if param_meta and param_meta.custom_decoder:
                decoder = param_meta.custom_decoder.decode
            else:
                decoder = txtdecoder_factory(param_type)
            req_param = RequestParam(
                name=name,
                alias=name,
                type_=param_type,
                annotation=annotation,
                decoder=cast(ITextDecoder[T], decoder),
                location="path",
                default=default,
            )
        elif self.is_plugin_type(param_type):
            return [PluginParam(type_=param_type, name=name, default=default)]
        elif is_body_param(param_type):
            if is_file_body(param_type):
                req_param = file_body_param(
                    name, param_type, annotation=annotation, default=default
                )
            else:
                if param_meta and param_meta.custom_decoder:
                    decoder = param_meta.custom_decoder.decode
                else:
                    decoder = decoder_factory(param_type)
                req_param = RequestBodyParam(
                    name=name,
                    alias=name,
                    annotation=annotation,
                    type_=param_type,
                    default=default,
                    decoder=cast(IDecoder[T], decoder),
                )
        elif param_type in self.graph.nodes:
            node = self.graph.analyze(cast(type, param_type))
            params: list[ParsedParam[Any]] = [node]
            for dep_name, dep in node.dependencies.items():
                ptype, dep_dfault = dep.param_type, dep.default_
                if dep_dfault is IDIDI_MISSING:
                    default = MISSING
                if ptype in self.graph.nodes:
                    # only add top level dependency, leave subs to ididi
                    continue
                ptype = cast(type, ptype)
                sub_params = self.parse_param(dep_name, ptype, default)
                params.extend(sub_params)
            return params

        elif param_meta and param_meta.factory:  # Annotated[Dep, use(dep_factory)]
            assert param_meta.config
            node = self.graph.analyze(param_meta.factory, config=param_meta.config)
            return self._parse_node(node)
        else:  # default case, treat as query
            if param_meta and param_meta.custom_decoder:
                decoder = param_meta.custom_decoder.decode
            else:
                decoder = txtdecoder_factory(param_type)
            req_param = RequestParam(
                name=name,
                alias=name,
                type_=param_type,
                annotation=annotation,
                decoder=cast(ITextDecoder[Any], decoder),
                location="query",
                default=default,
            )
        return req_param

    def _parse_node(self, node: DependentNode) -> list[ParsedParam[Any]]:
        params: list[Any | DependentNode] = [node]
        for dep_name, dep in node.dependencies.items():
            ptype, default = dep.param_type, dep.default_
            ptype = cast(type, ptype)
            sub_params = self.parse_param(dep_name, ptype, default)
            params.extend(sub_params)
        return params

    def _parse_marked[T](
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_meta: ParamMetas,
    ) -> ParsedParam[T] | list[ParsedParam[T]]:
        custom_decoder = param_meta.custom_decoder

        mark_type = param_meta.mark_type

        if mark_type == "use":
            node = self.graph.analyze(type_)
            return self._parse_node(node)
        else:
            # Easy case, Pure non-deps request params with param marks.
            location: ParamLocation
            alias = name
            content_type: BodyContentType = "application/json"

            if mark_type == "header":
                location = "header"
                alias = parse_header_key(name, param_meta.metas)
            elif mark_type == "body":
                body_param = RequestBodyParam(
                    name=name,
                    alias=alias,
                    type_=type_,
                    annotation=annotation,
                    default=default,
                    decoder=decoder_factory(type_),
                    content_type=content_type,
                )
                return body_param
            elif mark_type == "form":
                content_type = "multipart/form-data"
                decoder = custom_decoder or formdecoder_factory(type_)
                body_param = RequestBodyParam(
                    name=name,
                    alias=alias,
                    type_=type_,
                    annotation=annotation,
                    default=default,
                    decoder=cast(IFormDecoder[Any], decoder),
                    content_type=content_type,
                )
                return body_param
            elif mark_type == "path":
                location = "path"
            else:
                location = "query"

            txtdecoder = custom_decoder or txtdecoder_factory(type_)
            req_param = RequestParam(
                name=name,
                alias=alias,
                type_=type_,
                annotation=annotation,
                decoder=cast(ITextDecoder[Any], txtdecoder),
                location=location,
                default=default,
            )
            return req_param

    def parse_param[T](
        self,
        name: str,
        annotation: type[T] | UnionType | GenericAlias | TypeAliasType,
        default: Maybe[T] = MISSING,
    ) -> list[ParsedParam[T]]:
        parsed_type, pmetas = get_origin_pro(annotation)
        param_meta = ParamMetas.from_metas(pmetas) if pmetas else None
        if param_meta is None or not param_meta.mark_type:  # non generic version
            res = self._parse_rule_based(
                name=name,
                param_type=parsed_type,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )
        elif provider := self.plugin_provider.get(param_meta.mark_type):
            res = provider.parse(
                name=name,
                type_=parsed_type,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )
            res = cast(list[ParsedParam[T]], res)
        else:
            res = self._parse_marked(
                name=name,
                type_=parsed_type,
                annotation=annotation,
                default=default,
                param_meta=param_meta,
            )
        return res if isinstance(res, list) else [res]

    def parse(
        self,
        func_params: Sequence[tuple[str, Parameter]],
        path_keys: tuple[str, ...] | None = None,
    ) -> "EndpointParams":
        if path_keys:
            self.path_keys += path_keys

        params = dict[str, RequestParam[Any]]()
        bodies = dict[str, RequestBodyParam[Any]]()
        nodes = dict[str, DependentNode]()
        plugins = dict[str, PluginParam[Any]]()

        for name, param in func_params:
            annotation, default = param.annotation, param.default
            default = MISSING if param.default is Parameter.empty else param.default
            parsed_params = self.parse_param(name, annotation, default)

            for req_param in parsed_params:
                if isinstance(req_param, DependentNode):
                    nodes[name] = req_param
                    continue
                if isinstance(req_param, PluginParam):
                    plugins[req_param.name] = req_param
                elif isinstance(req_param, RequestBodyParam):
                    bodies[req_param.name] = req_param
                else:
                    params[req_param.name] = req_param

        if self.seen:
            warn(f"Unused path keys {self.seen}")

        return EndpointParams(
            params=params, bodies=bodies, nodes=nodes, plugins=plugins
        )
