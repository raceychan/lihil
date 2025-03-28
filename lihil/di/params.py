from copy import deepcopy
from inspect import Parameter
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    Sequence,
    TypeAliasType,
    TypeGuard,
    Union,
    cast,
    get_args,
)
from warnings import warn

from ididi import DependentNode, Graph, Resolver
from ididi.config import USE_FACTORY_MARK
from ididi.utils.param_utils import MISSING as IDIDI_MISSING
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
from lihil.interface.marks import (
    Body,
    Form,
    Header,
    Path,
    Query,
    Struct,
    Use,
    is_param_mark,
    lhl_get_origin,
)
from lihil.interface.struct import Base, IDecoder, IFormDecoder, ITextDecoder
from lihil.plugins.bus import EventBus
from lihil.utils.parse import parse_header_key
from lihil.utils.phasing import build_union_decoder, decoder_factory, to_bytes, to_str
from lihil.utils.typing import (
    deannotate,
    get_origin_pro,
    is_nontextual_sequence,
    is_union_type,
)
from lihil.vendor_types import FormData, Request, UploadFile

type ParamPair = tuple[str, RequestParam[Any] | RequestBodyParam[Any]] | tuple[
    str, PluginParam[Any]
]
type RequiredParams = Sequence[ParamPair]


def is_lhl_dep(
    param_type: type | GenericAlias,
) -> TypeGuard[type[Request | EventBus | Resolver]]:
    "Dependencies that should be injected and managed by lihil"
    if not isinstance(param_type, type):
        param_type = lhl_get_origin(param_type) or param_type
        param_type = cast(type, param_type)
    return issubclass(param_type, (Request, EventBus, Resolver))


def is_file_body(annt: Any) -> TypeGuard[type[UploadFile]]:
    annt_origin = lhl_get_origin(annt) or annt
    return annt_origin is UploadFile


def is_body_param(annt: Any) -> bool:
    if not isinstance(annt, type):
        return False

    if is_lhl_dep(annt):
        return False
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
    default: Maybe[Any] = MISSING
    required: bool = False
    # meta: ParamMeta | None = None

    def __post_init__(self):
        self.required = self.default is MISSING


class RequestParam[T](RequestParamBase[T], kw_only=True):
    text_decoder: ITextDecoder[T]
    location: ParamLocation

    def __repr__(self) -> str:
        type_repr = getattr(self.type_, "__name__", repr(self.type_))
        return f"RequestParam<{self.location}>({self.name}: {type_repr})"

    def decode(self, content: str) -> T:
        return self.text_decoder(content)


class RequestBodyParam[T](RequestParamBase[T], kw_only=True):
    decoder: IDecoder[T] | IFormDecoder[T]
    content_type: BodyContentType = "application/json"

    def __repr__(self) -> str:
        type_repr = getattr(self.type_, "__name__", repr(self.type_))
        return f"RequestBodyParam<{self.content_type}>({self.name}: {type_repr})"


class PluginParam[T](Base):
    type_: type[T]
    name: str
    default: Maybe[Any] = MISSING
    required: bool = False

    def __post_init__(self):
        self.required = self.default is MISSING


def analyze_nodeparams(
    node: DependentNode, graph: Graph, seen: set[str], path_keys: tuple[str, ...]
):
    params: list[ParamPair | DependentNode] = [node]
    for dep_name, dep in node.dependencies.items():
        ptype, default = dep.param_type, dep.default_
        ptype = cast(type, ptype)
        sub_params = analyze_param(graph, dep_name, seen, path_keys, ptype, default)
        params.extend(sub_params)
    return params


def analyze_annoated(
    graph: Graph,
    name: str,
    seen: set[str],
    path_keys: tuple[str, ...],
    default: Any,
    atype: type,
    metas: list[Any],
) -> list[ParamPair | DependentNode]:
    if metas and (USE_FACTORY_MARK in metas):
        idx = metas.index(USE_FACTORY_MARK)
        factory, config = metas[idx + 1], metas[idx + 2]
        node = graph.analyze(factory, config=config)
        return analyze_nodeparams(node, graph, seen, path_keys)
    elif new_origin := lhl_get_origin(atype):
        return analyze_markedparam(
            graph,
            name,
            seen,
            path_keys,
            type_=atype,
            porigin=new_origin,
            default=default,
            metas=metas,
        )
    else:
        return analyze_param(
            graph,
            name,
            seen,
            path_keys,
            atype,
            default,
            metas=metas,
        )


def analyze_markedparam(
    graph: Graph,
    name: str,
    seen: set[str],
    path_keys: tuple[str, ...],
    type_: type[Any] | UnionType | GenericAlias,
    porigin: Maybe[Query[Any] | Header[Any, Any] | Use[Any] | Annotated[Any, ...]],
    metas: list[Any],
    default: Any = MISSING,
) -> list[ParamPair | DependentNode]:

    atype, local_metas = deannotate(type_)
    if local_metas:
        metas += local_metas

    custom_decoder = get_decoder_from_metas(metas)

    if porigin is Use:
        node = graph.analyze(atype)
        return analyze_nodeparams(node, graph, seen, path_keys)
    else:
        # Easy case, Pure non-deps request params with param marks.
        location: ParamLocation
        alias = name
        content_type: BodyContentType = "application/json"
        if porigin is Header:
            location = "header"
            alias = parse_header_key(name, metas)
        elif porigin is Body:
            body_param = RequestBodyParam(
                name=name,
                alias=alias,
                type_=type_,
                default=default,
                decoder=decoder_factory(atype),
                content_type=content_type,
            )
            return [(name, body_param)]
        elif porigin is Form:
            content_type = "multipart/form-data"
            decoder = custom_decoder or formdecoder_factory(atype)
            body_param = RequestBodyParam(
                name=name,
                alias=alias,
                type_=atype,
                default=default,
                decoder=cast(IFormDecoder[Any], decoder),
                content_type=content_type,
            )
            return [(name, body_param)]
        elif porigin is Path:
            location = "path"
        else:
            location = "query"

        txtdecoder = custom_decoder or txtdecoder_factory(atype)
        req_param = RequestParam(
            type_=atype,
            name=name,
            alias=alias,
            text_decoder=cast(ITextDecoder[Any], txtdecoder),
            location=location,
            default=default,
        )
        pair = (name, req_param)
        return [pair]


def file_body_param(
    name: str, type_: type[UploadFile], default: Any
) -> RequestBodyParam[Any]:
    decoder = filedeocder_factory(name)
    content_type = "multipart/form-data"

    req_param = RequestBodyParam(
        type_=type_,
        name=name,
        alias=name,
        decoder=decoder,
        default=default,
        content_type=content_type,
    )
    return req_param


def analyze_union_param(
    name: str, type_: UnionType | type[Any] | GenericAlias, default: Any
) -> RequestParam[Any] | RequestBodyParam[Any]:
    type_args = get_args(type_)

    for subt in type_args:
        if is_body_param(subt):
            if is_file_body(type_):
                return file_body_param(name, type_=type_, default=default)
            decoder = decoder_factory(subt)
            req_param = RequestBodyParam(
                type_=type_,
                name=name,
                alias=name,
                decoder=decoder,
                default=default,
            )
            return req_param
    else:
        txt_decoder = cast(ITextDecoder[Any], txtdecoder_factory(type_))
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            text_decoder=txt_decoder,
            location="query",
            default=default,
        )
    return req_param


def get_decoder_from_metas(
    metas: list[Any],
) -> ITextDecoder[Any] | IDecoder[Any] | IFormDecoder[Any] | None:
    # TODO: custom convertor
    for meta in metas:
        if isinstance(meta, CustomDecoder):
            return meta.decode


def analyze_param[T](
    graph: Graph,
    name: str,
    seen: set[str],
    path_keys: tuple[str, ...],
    type_: type[T] | UnionType | GenericAlias,  # or GenericAlias
    default: Maybe[T] = MISSING,
    metas: list[Any] | None = None,
) -> list[ParamPair | DependentNode]:
    """
    Analyzes a parameter and returns a tuple of:
    - A list of request parameters extracted from this parameter and its dependencies
    - The dependent node if this parameter is a dependency, otherwise None
    """

    custom_decoder = get_decoder_from_metas(metas) if metas else None
    if (porigin := lhl_get_origin(type_)) is Annotated:
        atype, metas = deannotate(type_)
        return analyze_annoated(
            graph=graph,
            name=name,
            seen=seen,
            path_keys=path_keys,
            atype=atype,
            default=default,
            metas=metas or [],
        )

    if is_param_mark(type_):
        return analyze_markedparam(
            graph=graph,
            name=name,
            seen=seen,
            path_keys=path_keys,
            type_=type_,
            porigin=porigin,
            default=default,
            metas=metas or [],
        )

    if name in path_keys:  # simplest case
        seen.discard(name)
        txtdecoder = custom_decoder or txtdecoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            text_decoder=cast(ITextDecoder[Any], txtdecoder),
            location="path",
            default=default,
        )
    elif is_body_param(type_):
        if is_file_body(type_):
            req_param = file_body_param(name, type_, default)
        else:
            decoder = custom_decoder or decoder_factory(type_)
            req_param = RequestBodyParam(
                type_=type_,
                name=name,
                default=default,
                alias=name,
                decoder=cast(IDecoder[Any], decoder),
            )
    elif isinstance(type_, UnionType) or lhl_get_origin(type_) is Union:
        req_param = analyze_union_param(name, type_, default)
    elif type_ in graph.nodes:
        node = graph.analyze(cast(type, type_))
        params: list[ParamPair | DependentNode] = [node]
        for dep_name, dep in node.dependencies.items():
            ptype, dep_dfault = dep.param_type, dep.default_
            if dep_dfault is IDIDI_MISSING:
                default = MISSING
            if ptype in graph.nodes:
                # only add top level dependency, leave subs to ididi
                continue
            ptype = cast(type, ptype)
            sub_params = analyze_param(graph, dep_name, seen, path_keys, ptype, default)
            params.extend(sub_params)
        return params

    elif is_lhl_dep(type_):
        # user should be able to menually init their plugin then register as a singleton
        return [(name, PluginParam(type_=type_, name=name, default=default))]
    else:  # default case, treat as query
        txtdecoder = custom_decoder or txtdecoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            text_decoder=cast(ITextDecoder[Any], txtdecoder),
            location="query",
            default=default,
        )
    return [(name, req_param)]


# """
# class PluginLoader(Protocol):
#     def is_plugin(self, param) -> bool:
#         ...

#     def inject_plugin(self, param, request, resolver):
#         ...
# """


def contains_mark(metas: list[Any]):
    for m in meats:
        if m is USE_FACTORY_MARK:
            return True
        elif is_param_mark(m):
            return True
    return False


class ParamParser:

    def __init__(
        self,
        graph: Graph,
        seen: set[str],
        path_keys: tuple[str],
        plugin_types: tuple[type, ...],
    ):
        self.graph = graph
        self.seen = seen
        self.path_keys = path_keys
        self.plugin_types = plugin_types

        self.parsed_params = EndpointParams()

    def is_plugin_type(self, param_type: Any):
        if not isinstance(param_type, type):
            param_type = lhl_get_origin(param_type) or param_type
            param_type = cast(type, param_type)
        return issubclass(param_type, self.plugin_types)

    def parse_rule_based[T](
        self, name: str, param_type: type[T] | UnionType, default: Maybe[T]
    ) -> list[ParamPair | DependentNode]:
        if name in self.path_keys:  # simplest case
            self.seen.discard(name)
            txtdecoder = txtdecoder_factory(param_type)
            req_param = RequestParam(
                type_=param_type,
                name=name,
                alias=name,
                text_decoder=cast(ITextDecoder[Any], txtdecoder),
                location="path",
                default=default,
            )
        elif is_body_param(param_type):
            if is_file_body(param_type):
                req_param = file_body_param(name, param_type, default)
            else:
                decoder = decoder_factory(param_type)
                req_param = RequestBodyParam(
                    type_=param_type,
                    name=name,
                    default=default,
                    alias=name,
                    decoder=decoder,
                )
        elif isinstance(param_type, UnionType) or lhl_get_origin(param_type) is Union:
            req_param = analyze_union_param(name, param_type, default)
        elif param_type in self.graph.nodes:
            node = self.graph.analyze(cast(type, param_type))
            params: list[ParamPair | DependentNode] = [node]
            for dep_name, dep in node.dependencies.items():
                ptype, dep_dfault = dep.param_type, dep.default_
                if dep_dfault is IDIDI_MISSING:
                    default = MISSING
                if ptype in self.graph.nodes:
                    # only add top level dependency, leave subs to ididi
                    continue
                ptype = cast(type, ptype)
                sub_params = analyze_param(
                    self.graph, dep_name, self.seen, self.path_keys, ptype, default
                )
                params.extend(sub_params)
            return params

        elif self.is_plugin_type(param_type):
            # user should be able to menually init their plugin then register as a singleton
            return [(name, PluginParam(type_=param_type, name=name, default=default))]
        else:  # default case, treat as query
            txtdecoder = txtdecoder_factory(param_type)
            req_param = RequestParam(
                type_=param_type,
                name=name,
                alias=name,
                text_decoder=cast(ITextDecoder[Any], txtdecoder),
                location="query",
                default=default,
            )
        return [(name, req_param)]

    def parse_marked[T](
        self, name: str, type_: type[T], default: Maybe[T], metas: list[Any]
    ):
        breakpoint()

    def parse_generic(self): ...

    def parse_param[T](
        self,
        name: str,
        type_: type[T] | UnionType | GenericAlias | TypeAliasType,
        default: Maybe[T] = MISSING,
    ):
        porigin, pmetas = get_origin_pro(type_)

        if not pmetas:  # non generic version
            res = self.parse_rule_based(name, porigin, default)
        elif contains_mark(pmetas):
            res = self.parse_marked(name, porigin, default, pmetas)
        else:
            res = self.parse_generic()

        self.parsed_params.collect_param(name, res)


class EndpointParams(Base):
    params: dict[str, RequestParam[Any]] = field(default_factory=dict)
    bodies: dict[str, RequestBodyParam[Any]] = field(default_factory=dict)
    nodes: dict[str, DependentNode] = field(default_factory=dict)
    plugins: dict[str, PluginParam[Any]] = field(default_factory=dict)

    def collect_param(self, name: str, param_list: list[ParamPair | DependentNode]):
        for element in param_list:
            if isinstance(element, DependentNode):
                self.nodes[name] = element
            else:
                param_name, req_param = element
                if isinstance(req_param, PluginParam):
                    self.plugins[param_name] = req_param
                elif isinstance(req_param, RequestBodyParam):
                    self.bodies[param_name] = req_param
                else:
                    self.params[param_name] = req_param

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

    @classmethod
    def from_func_params(
        cls,
        func_params: tuple[tuple[str, Parameter], ...],
        graph: Graph,
        path_keys: tuple[str],
    ):
        seen_path = set(path_keys)
        params = dict[str, RequestParam[Any]]()
        bodies = dict[str, RequestBodyParam[Any]]()
        nodes = dict[str, DependentNode]()
        plugins = dict[str, PluginParam[Any]]()
        for name, param in func_params:
            ptype, default = param.annotation, param.default
            default = MISSING if param.default is Parameter.empty else param.default
            param_list = analyze_param(
                graph=graph,
                name=name,
                seen=seen_path,
                path_keys=path_keys,
                type_=ptype,
                default=default,
            )
            for element in param_list:
                if isinstance(element, DependentNode):
                    nodes[name] = element
                    continue
                param_name, req_param = element
                if isinstance(req_param, PluginParam):
                    plugins[param_name] = req_param
                elif isinstance(req_param, RequestBodyParam):
                    bodies[param_name] = req_param
                else:
                    params[param_name] = req_param
        if seen_path:
            warn(f"Unused path keys {seen_path}")
        return cls(params=params, bodies=bodies, nodes=nodes, plugins=plugins)

    # @classmethod
    # def from_func_params(
    #     cls,
    #     func_params: tuple[tuple[str, Parameter], ...],
    #     graph: Graph,
    #     path_keys: tuple[str],
    # ):
    #     seen_path = set(path_keys)
    #     params = dict[str, RequestParam[Any]]()
    #     bodies = dict[str, RequestBodyParam[Any]]()
    #     nodes = dict[str, DependentNode]()
    #     plugins = dict[str, PluginParam[Any]]()

    #     plugin_types = (Request, EventBus, Resolver)
    #     parser = ParamParser(graph, seen_path, path_keys, plugin_types=plugin_types)

    #     for name, param in func_params:
    #         ptype, pdefault = param.annotation, param.default
    #         default = MISSING if pdefault is Parameter.empty else pdefault
    #         parser.parse_param(name, ptype, default)

    #     return cls(params=params, bodies=bodies, nodes=nodes, plugins=plugins)
