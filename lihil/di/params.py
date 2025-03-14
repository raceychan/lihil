from inspect import Parameter
from types import UnionType
from typing import Annotated, Any, Callable, Sequence, cast, get_args, get_origin

from ididi import DependentNode, Graph
from ididi.config import USE_FACTORY_MARK
from msgspec import Meta as ParamMeta
from msgspec import field

from lihil.config import is_lhl_dep
from lihil.interface import MISSING, Base, IDecoder, ITextDecoder, Maybe, ParamLocation
from lihil.interface.marks import Body, Header, Path, Payload, Query, Use
from lihil.utils.parse import parse_header_key
from lihil.utils.phasing import decoder_factory, textdecoder_factory
from lihil.utils.typing import flatten_annotated

# from starlette.requests import Request


type ParamPair = tuple[str, RequestParam[Any]] | tuple[str, SingletonParam[Any]]
type RequiredParams = Sequence[ParamPair]


class CustomDecoder:
    """
    class IType: ...

    def decode_itype()


    async def create_user(i: Annotated[IType, CustomDecoder(decode_itype)])
    """

    decode: Callable[[bytes | str], Any]


class RequestParamBase[T](Base):
    type_: type[T] | UnionType
    name: str
    default: Maybe[Any] = MISSING
    required: bool = False

    def __post_init__(self):
        self.required = self.default is MISSING


class RequestParam[T](RequestParamBase[T], kw_only=True):
    """
    maybe we would like to create a subclass RequestBody
    since RequestBody can have content-type
    reff:
    https://stackoverflow.com/questions/4526273/what-does-enctype-multipart-form-data-mean
    """

    # content_type: Literal["application/json", "multipart/form-data"], related to decoder

    alias: str
    decoder: IDecoder[T] | ITextDecoder[T]
    location: ParamLocation
    meta: ParamMeta | None = None

    def __repr__(self) -> str:
        type_repr = getattr(self.type_, "__name__", repr(self.type_))
        return f"RequestParam<{self.location}>({self.name}: {type_repr})"

    def decode(self, content: bytes | str) -> T:
        return self.decoder(content)


class SingletonParam[T](RequestParamBase[T]): ...


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
            raise NotImplementedError()
        return body_param


def analyze_nodeparams(
    node: DependentNode, graph: Graph, seen: set[str], path_keys: tuple[str]
):
    params: list[ParamPair | DependentNode] = [node]
    for dep_name, dep in node.dependencies.items():
        ptype, default = dep.param_type, dep.default_
        ptype = cast(type, ptype)
        sub_params = analyze_param(graph, dep_name, seen, path_keys, ptype, default)
        params.extend(sub_params)
    return params


def analyze_markedparam(
    graph: Graph,
    name: str,
    seen: set[str],
    path_keys: tuple[str],
    type_: type[Any] | UnionType,
    porigin: Query[Any] | Header[Any, Any] | Use[Any] | Annotated[Any, ...],
    default: Any,
) -> list[ParamPair | DependentNode]:
    atype, *metas = flatten_annotated(type_)
    if porigin is Annotated:
        if USE_FACTORY_MARK in metas:
            idx = metas.index(USE_FACTORY_MARK)
            factory, config = metas[idx + 1], metas[idx + 2]
            node = graph.analyze(factory, config=config)
            return analyze_nodeparams(node, graph, seen, path_keys)
        elif new_origin := get_origin(atype):
            return analyze_markedparam(
                graph, name, seen, path_keys, atype, new_origin, default
            )
        else:
            return analyze_param(graph, name, seen, path_keys, atype, default)
    elif porigin is Use:
        node = graph.analyze(atype)
        return analyze_nodeparams(node, graph, seen, path_keys)
    else:
        # Pure non-deps request params
        location: ParamLocation
        alias = name
        custom_decoder = None
        for meta in metas:
            if isinstance(meta, CustomDecoder):
                custom_decoder = meta.decode
                break

        if porigin is Header:
            location = "header"
            alias = parse_header_key(name, metas)
        elif porigin is Body:
            location = "body"
        elif porigin is Path:
            location = "path"
        else:
            location = "query"

        if custom_decoder:
            decoder = custom_decoder
        else:
            if location == "body":
                decoder = decoder_factory(atype)
            else:
                decoder = textdecoder_factory(atype)

        req_param = RequestParam(
            type_=atype,
            name=name,
            alias=alias,
            decoder=decoder,
            location=location,
            default=default,
        )
        pair = (name, req_param)
        return [pair]


def analyze_param(
    graph: Graph,
    name: str,
    seen: set[str],
    path_keys: tuple[str],
    type_: type[Any] | UnionType,
    default: Any,
) -> list[ParamPair | DependentNode]:
    """
    Analyzes a parameter and returns a tuple of:
    - A list of request parameters extracted from this parameter and its dependencies
    - The dependent node if this parameter is a dependency, otherwise None
    """

    if name in path_keys:  # simplest case
        seen.discard(name)
        decoder = textdecoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            decoder=decoder,
            location="path",
            default=default,
        )
    elif isinstance(type_, type) and issubclass(type_, Payload):
        decoder = decoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            decoder=decoder,
            location="body",
            default=default,
        )
    elif isinstance(type_, UnionType):
        type_args = get_args(type_)
        if any(issubclass(subt, Payload) for subt in type_args):
            decoder = decoder_factory(type_)
            req_param = RequestParam(
                type_=type_,
                name=name,
                alias=name,
                decoder=decoder,
                location="body",
                default=default,
            )
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

    elif type_ in graph.nodes:
        node = graph.analyze(type_)
        params: list[ParamPair | DependentNode] = [node]
        for dep_name, dep in node.dependencies.items():
            ptype, default = dep.param_type, dep.default_
            if ptype in graph.nodes:
                # only add top level dependency, leave subs to ididi
                continue
            ptype = cast(type, ptype)
            sub_params = analyze_param(graph, dep_name, seen, path_keys, ptype, default)
            params.extend(sub_params)
        return params
    elif porigin := get_origin(type_):
        return analyze_markedparam(
            graph, name, seen, path_keys, type_, porigin, default
        )
    elif is_lhl_dep(type_):
        # user should be able to menually init their plugin then register as a singleton
        return [(name, SingletonParam(type_=type_, name=name, default=default))]
    else:  # default case, treat as query
        decoder = textdecoder_factory(type_)
        req_param = RequestParam(
            type_=type_,
            name=name,
            alias=name,
            decoder=decoder,
            location="query",
            default=default,
        )
    return [(name, req_param)]


def analyze_request_params(
    func_params: tuple[Any, ...],
    graph: Graph,
    seen_path: set[str],
    path_keys: tuple[str],
) -> ParsedParams:
    parsed_params = ParsedParams()
    for name, param in func_params:
        ptype, default = param.annotation, param.default
        default = MISSING if param.default is Parameter.empty else param.default
        param_list = analyze_param(graph, name, seen_path, path_keys, ptype, default)
        parsed_params.collect_param(name, param_list)
    return parsed_params
