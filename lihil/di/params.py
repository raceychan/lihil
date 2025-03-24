from copy import deepcopy
from inspect import Parameter
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    Callable,
    Literal,
    Sequence,
    Union,
    cast,
    get_args,
    get_origin,
)

from ididi import DependentNode, Graph
from ididi.config import USE_FACTORY_MARK
from ididi.utils.param_utils import MISSING as IDIDI_MISSING
from msgspec import convert, field
from msgspec.structs import fields as get_fields
from starlette.datastructures import FormData

from lihil.interface import MISSING, Base, IDecoder, Maybe, ParamLocation
from lihil.interface.marks import (
    Body,
    Form,
    Header,
    Path,
    Query,
    Struct,
    Use,
    is_param_mark,
)
from lihil.plugins.bus import EventBus
from lihil.utils.parse import parse_header_key
from lihil.utils.phasing import build_union_decoder, decoder_factory, to_bytes, to_str
from lihil.utils.typing import flatten_annotated, is_nontextual_sequence, is_union_type
from lihil.vendor_types import FormData, Request, UploadFile

type ParamPair = tuple[str, RequestParam[Any]] | tuple[str, SingletonParam[Any]]
type RequiredParams = Sequence[ParamPair]


def is_lhl_dep(type_: type | GenericAlias):
    "Dependencies that should be injected and managed by lihil"
    return type_ in (Request, EventBus)


def is_file_body(annt: Any) -> bool:
    annt_origin = get_origin(annt) or annt
    return annt_origin is UploadFile


def is_body_param(annt: Any) -> bool:

    if not isinstance(annt, type):
        return False

    if is_lhl_dep(annt):
        return False

    return issubclass(annt, Struct) or is_file_body(annt)


def textdecoder_factory(
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

        raise NotImplementedError(
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


class CustomDecoder(Base):
    """
    class IType: ...

    def decode_itype()


    async def create_user(i: Annotated[IType, CustomDecoder(decode_itype)])
    """

    decode: Callable[[bytes | str], Any]


class RequestParamBase[T](Base):
    type_: type[T] | UnionType | GenericAlias
    name: str
    default: Maybe[Any] = MISSING
    required: bool = False

    def __post_init__(self):
        self.required = self.default is MISSING


class ParamMeta(Base):
    is_form_body: bool


type ParamContentType = Literal[
    "application/json", "multipart/form-data", "application/x-www-form-urlencoded"
]


class RequestParam[T](RequestParamBase[T], kw_only=True):
    """
    maybe we would like to create a subclass RequestBody
    since RequestBody can have content-type
    reff:
    https://stackoverflow.com/questions/4526273/what-does-enctype-multipart-form-data-mean
    """

    alias: str
    decoder: IDecoder[T]
    location: ParamLocation
    content_type: ParamContentType = "application/json"
    # meta: ParamMeta | None = None

    def __repr__(self) -> str:
        type_repr = getattr(self.type_, "__name__", repr(self.type_))
        return f"RequestParam<{self.location}>({self.name}: {type_repr})"

    def decode(self, content: bytes | str) -> T:
        return self.decoder(content)


class SingletonParam[T](RequestParamBase[T]): ...


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
    elif new_origin := get_origin(atype):
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

    atype, local_metas = flatten_annotated(type_)
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
        content_type: ParamContentType = "application/json"
        if porigin is Header:
            location = "header"
            alias = parse_header_key(name, metas)
        elif porigin is Body:
            location = "body"
        elif porigin is Form:
            location = "body"
            content_type = "multipart/form-data"
            custom_decoder = formdecoder_factory(atype)
        elif porigin is Path:
            location = "path"
        else:
            location = "query"

        if custom_decoder is None:
            if location == "body":
                decoder = decoder_factory(atype)
            else:
                decoder = textdecoder_factory(atype)
        else:
            decoder = custom_decoder

        req_param = RequestParam(
            type_=atype,
            name=name,
            alias=alias,
            decoder=decoder,
            location=location,
            default=default,
            content_type=content_type,
        )
        pair = (name, req_param)
        return [pair]


def file_body_param(
    name: str, type_: UnionType | type[UploadFile] | GenericAlias, default: Any
):
    decoder = filedeocder_factory(name)
    content_type = "multipart/form-data"

    req_param = RequestParam(
        type_=type_,
        name=name,
        alias=name,
        decoder=decoder,
        location="body",
        default=default,
        content_type=content_type,
    )
    return req_param


def analyze_union_param(
    name: str, type_: UnionType | type[Any] | GenericAlias, default: Any
) -> RequestParam[Any]:
    type_args = get_args(type_)
    content_type: ParamContentType = "application/json"

    for subt in type_args:
        if is_body_param(subt):
            if is_file_body(type_):
                return file_body_param(name, type_=type_, default=default)
            decoder = decoder_factory(subt)
            req_param = RequestParam(
                type_=type_,
                name=name,
                alias=name,
                decoder=decoder,
                location="body",
                default=default,
                content_type=content_type,
            )
            break
    else:
        decoder = textdecoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            decoder=decoder,
            location="query",
            default=default,
        )
    return req_param


def get_decoder_from_metas(metas: list[Any]) -> IDecoder[Any] | None:
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
    content_type: ParamContentType = "application/json",
    metas: list[Any] | None = None,
) -> list[ParamPair | DependentNode]:
    """
    Analyzes a parameter and returns a tuple of:
    - A list of request parameters extracted from this parameter and its dependencies
    - The dependent node if this parameter is a dependency, otherwise None
    """

    custom_decoder = get_decoder_from_metas(metas) if metas else None

    if (porigin := get_origin(type_)) is Annotated:
        atype, metas = flatten_annotated(type_)
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
        decoder = custom_decoder or textdecoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            decoder=decoder,
            location="path",
            default=default,
        )
    elif is_body_param(type_):
        if is_file_body(type_):
            req_param = file_body_param(name, cast(type[UploadFile], type_), default)
        else:
            decoder = custom_decoder or decoder_factory(type_)
            req_param = RequestParam(
                type_=type_,
                name=name,
                default=default,
                alias=name,
                decoder=decoder,
                location="body",
                content_type=content_type,
            )
    elif isinstance(type_, UnionType) or get_origin(type_) is Union:
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
        return [(name, SingletonParam(type_=type_, name=name, default=default))]
    else:  # default case, treat as query
        decoder = custom_decoder or textdecoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            decoder=decoder,
            location="query",
            default=default,
        )
    return [(name, req_param)]


class ParsedParams(Base):
    params: list[tuple[str, RequestParam[Any]]] = field(default_factory=list)
    bodies: list[tuple[str, RequestParam[Any]]] = field(default_factory=list)
    # nodes should be a dict with {name: node}
    nodes: list[tuple[str, DependentNode]] = field(default_factory=list)
    singletons: list[tuple[str, SingletonParam[Any]]] = field(default_factory=list)

    def collect_param(self, name: str, param_list: list[ParamPair | DependentNode]):
        for element in param_list:
            if isinstance(element, DependentNode):
                self.nodes.append((name, element))
            else:
                param_name, req_param = element
                if isinstance(req_param, SingletonParam):
                    self.singletons.append((param_name, req_param))
                elif req_param.location == "body":
                    self.bodies.append((param_name, req_param))
                else:
                    self.params.append((param_name, req_param))

    def get_location(
        self, location: ParamLocation
    ) -> tuple[tuple[str, RequestParam[Any]], ...]:
        return tuple(p for p in self.params if p[1].location == location)

    def get_body(self) -> tuple[str, RequestParam[Any]] | None:
        if not self.bodies:
            body_param = None
        elif len(self.bodies) == 1:
            body_param = self.bodies[0]
        else:
            # "use defstruct to dynamically define a type"
            raise NotImplementedError(
                "endpoint with multiple body params is not yet supported"
            )
        return body_param


def analyze_request_params(
    func_params: tuple[tuple[str, Parameter], ...],
    graph: Graph,
    seen_path: set[str],
    path_keys: tuple[str],
) -> ParsedParams:
    parsed_params = ParsedParams()
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
        parsed_params.collect_param(name, param_list)
    return parsed_params
