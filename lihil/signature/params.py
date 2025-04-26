from copy import deepcopy
from inspect import Parameter, signature
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    Mapping,
    TypeAliasType,
    TypeGuard,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)
from warnings import warn

from ididi import DependentNode, Graph, INode, NodeConfig, Resolver
from ididi.config import USE_FACTORY_MARK
from ididi.utils.param_utils import MISSING as IDIDI_MISSING
from ididi.utils.typing_utils import is_builtin_type
from msgspec import UNSET, DecodeError
from msgspec import Meta as ParamConstraint
from msgspec import Struct, ValidationError, convert, field
from msgspec.structs import fields as get_fields
from starlette.datastructures import FormData

from lihil.config import AppConfig
from lihil.errors import MissingDependencyError, NotSupportedError
from lihil.interface import MISSING as LIHIL_MISSING
from lihil.interface import (
    BodyContentType,
    CustomDecoder,
    Maybe,
    ParamBase,
    ParamLocation,
    RegularTypes,
    is_provided,
)
from lihil.interface.marks import (
    HEADER_REQUEST_MARK,
    JW_TOKEN_RETURN_MARK,
    ParamMarkType,
    Struct,
    extract_mark_type,
)
from lihil.interface.struct import Base, IDecoder, IFormDecoder
from lihil.plugins.bus import EventBus
from lihil.plugins.registry import PLUGIN_REGISTRY, PluginBase, PluginParam
from lihil.problems import (
    CustomDecodeErrorMessage,
    CustomValidationError,
    InvalidDataType,
    InvalidJsonReceived,
    MissingRequestParam,
    ValidationProblem,
)
from lihil.utils.json import decoder_factory
from lihil.utils.string import parse_header_key, to_kebab_case
from lihil.utils.typing import (
    get_origin_pro,
    is_mapping_type,
    is_nontextual_sequence,
    is_union_type,
)
from lihil.vendors import FormData, Headers, QueryParams, Request, UploadFile, WebSocket

type RequestParam[T] = PathParam[T] | QueryParam[T] | HeaderParam[T] | CookieParam[T]
type ParsedParam[T] = RequestParam[T] | BodyParam[T] | DependentNode | PluginParam


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


def textdecoder_factory[T](
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
    def file_decoder(form_data: FormData) -> UploadFile | None:
        if upload_file := form_data.get(filename):
            return cast(UploadFile, upload_file)

    return file_decoder


def file_body_param(
    name: str, type_: type[UploadFile], annotation: Any, default: Any
) -> "BodyParam[UploadFile | None]":
    decoder = filedeocder_factory(name)
    content_type = "multipart/form-data"
    req_param = BodyParam(
        name=name,
        alias=name,
        type_=type_,
        annotation=annotation,
        decoder=decoder,
        default=default,
        content_type=content_type,
    )
    return req_param


def formdecoder_factory[T](
    ptype: type[T] | UnionType,
) -> IFormDecoder[T] | IDecoder[bytes, T]:

    def dummy_decoder(content: bytes) -> bytes:
        return content

    if not isinstance(ptype, type) or not issubclass(ptype, Struct):
        if ptype is bytes:
            return cast(IDecoder[bytes, T], dummy_decoder)

        raise NotSupportedError(
            f"Currently only bytes or subclass of Struct is supported for `Form`, received {ptype}"
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


type ParamResult[T] = tuple[T, None] | tuple[None, ValidationProblem]


class Decodable[D, T](ParamBase[T], kw_only=True):
    decoder: IDecoder[Any, T] = None  # type: ignore

    def __post_init__(self):
        super().__post_init__()

    def decode(self, content: D) -> T:
        """
        for decoder in self.decoders:
            contennt = decoder(content)
        """
        return self.decoder(content)

    def validate(self, raw: D) -> ParamResult[T]:
        try:
            value = self.decode(raw)
            return value, None
        except ValidationError as mve:
            error = InvalidDataType(self.location, self.name, str(mve))
        except DecodeError:
            error = InvalidJsonReceived(self.location, self.name)
        except CustomValidationError as cve:  # type: ignore
            error = CustomDecodeErrorMessage(self.location, self.name, cve.detail)
        return None, error


class PathParam[T](Decodable[str | list[str], T], kw_only=True):
    location: ClassVar[ParamLocation] = "path"

    def __post_init__(self):
        super().__post_init__()
        if not self.required:
            raise NotSupportedError(
                f"Path param {self} with default value is not supported"
            )

    def extract(self, params: dict[str, str]) -> ParamResult[T]:
        try:
            raw = params[self.alias]
        except KeyError:
            return (None, MissingRequestParam(self.location, self.alias))

        return self.validate(raw)


class QueryParam[T](Decodable[str | list[str], T]):
    location: ClassVar[ParamLocation] = "query"
    decoder: IDecoder[str | list[str], T] = None  # type: ignore
    multivals: bool = False

    def __post_init__(self):
        super().__post_init__()

        if is_mapping_type(self.type_):
            raise NotSupportedError(
                f"query param should not be declared as mapping type, or a union that contains mapping type, received: {self.type_}"
            )

        self.multivals = is_nontextual_sequence(self.type_)

    def extract(self, queries: QueryParams | Headers) -> ParamResult[T]:
        alias = self.alias
        if self.multivals:
            raw = queries.getlist(alias)
        else:
            raw = queries.get(alias)

        if raw is None:
            if is_provided(default := self.default):
                return (default, None)
            else:
                return (None, MissingRequestParam(self.location, alias))
        return self.validate(raw)


class HeaderParam[T](QueryParam[T]):
    location: ClassVar[ParamLocation] = "header"


class CookieParam[T](HeaderParam[T], kw_only=True):
    alias = "cookie"
    cookie_name: str


class BodyParam[T](Decodable[bytes | FormData, T], kw_only=True):
    location: ClassVar[ParamLocation] = "body"
    content_type: BodyContentType = "application/json"

    def __repr__(self) -> str:
        return f"BodyParam<{self.content_type}>({self.name}: {self.type_repr})"

    def extract(self, body: bytes | FormData) -> ParamResult[T]:
        if body == b"" or (isinstance(body, FormData) and len(body) == 0):
            if is_provided(default := self.default):
                val = default
                return (val, None)
            else:
                error = MissingRequestParam(self.location, self.alias)
                return (None, error)

        return self.validate(body)


class ParamMetasBase(Base):
    metas: list[Any]


class RequestParamMeta(ParamMetasBase):
    mark_type: ParamMarkType | None = None
    custom_decoder: IDecoder[Any, Any] | None = None
    constraint: ParamConstraint | None = None


class NodeParamMeta(ParamMetasBase, kw_only=True):
    factory: Maybe[INode[..., Any]]
    node_config: NodeConfig


class EndpointParams(Base, kw_only=True):
    params: dict[str, RequestParam[Any]] = field(default_factory=dict)
    bodies: dict[str, BodyParam[Any]] = field(default_factory=dict)
    nodes: dict[str, DependentNode] = field(default_factory=dict)
    plugins: dict[str, PluginParam] = field(default_factory=dict)

    @overload
    def get_location(
        self, location: Literal["header"]
    ) -> dict[str, HeaderParam[Any]]: ...

    @overload
    def get_location(
        self, location: Literal["query"]
    ) -> dict[str, QueryParam[Any]]: ...

    @overload
    def get_location(self, location: Literal["path"]) -> dict[str, PathParam[Any]]: ...

    def get_location(self, location: ParamLocation) -> Mapping[str, RequestParam[Any]]:
        return {n: p for n, p in self.params.items() if p.location == location}

    def get_body(self) -> tuple[str, BodyParam[Any]] | None:
        if not self.bodies:
            body_param = None
        elif len(self.bodies) == 1:
            body_param = next(iter(self.bodies.items()))
        else:
            # use defstruct to dynamically define a type
            raise NotSupportedError(
                "Endpoint with multiple body params is not supported"
            )
        return body_param


def req_param_factory[T](
    name: str,
    alias: str,
    param_type: type[T] | UnionType,
    annotation: Any,
    default: Maybe[T],
    decoder: IDecoder[str | list[str], T] | None = None,
    param_metas: RequestParamMeta | None = None,
    location: ParamLocation = "query",
) -> RequestParam[T]:

    if isinstance(param_metas, RequestParamMeta) and param_metas.constraint:
        param_type = cast(type[T], Annotated[param_type, param_metas.constraint])

    if decoder is None:
        if param_metas and param_metas.custom_decoder:
            decoder = param_metas.custom_decoder
        else:
            decoder = textdecoder_factory(param_type=param_type)

    if location == "path":
        req_param = PathParam(
            name=name,
            alias=alias,
            type_=param_type,
            annotation=annotation,
            decoder=decoder,
            default=default,
        )
    elif location == "header":
        if alias == "cookie":
            assert param_metas
            cookie_name = param_metas.metas[0]
            cookie_name = parse_header_key(name, cookie_name)
            return CookieParam(
                name=name,
                cookie_name=cookie_name,
                alias=alias,
                type_=param_type,
                annotation=annotation,
                decoder=decoder,
                default=default,
            )
        return HeaderParam(
            name=name,
            alias=alias,
            type_=param_type,
            annotation=annotation,
            decoder=decoder,
            default=default,
        )
    else:
        # elif location == "query":
        req_param = QueryParam(
            name=name,
            alias=alias,
            type_=param_type,
            annotation=annotation,
            decoder=decoder,
            default=default,
        )

    return req_param


class ParamParser:
    path_keys: tuple[str, ...]
    seen: set[str]

    def __init__(
        self,
        graph: Graph,
        path_keys: tuple[str, ...] | None = None,
        app_config: AppConfig | None = None,
    ):
        self.graph = graph

        if path_keys:
            self.path_keys = path_keys
            self.seen = set(self.path_keys)
        else:
            self.path_keys = ()
            self.seen = set()

        # mark_type or param_type, dict[str | type, PluginProvider]
        self.lhl_primitives = LIHIL_PRIMITIVES
        self.app_config = app_config

    def is_lhl_primitive(self, param_type: Any) -> TypeGuard[type]:
        "Dependencies that should be injected and managed by lihil"
        if not isinstance(param_type, type):
            param_origin = get_origin(param_type)
            if param_origin is Union:
                return any(self.is_lhl_primitive(arg) for arg in get_args(param_type))
            elif param_origin and is_builtin_type(param_origin):
                return False
            else:
                return self.is_lhl_primitive(type(param_type))
        else:
            return issubclass(param_type, self.lhl_primitives)

    def _parse_rule_based[T](
        self,
        name: str,
        param_type: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_metas: RequestParamMeta | None = None,
    ) -> ParsedParam[T] | list[ParsedParam[T]]:
        if name in self.path_keys:  # simplest case
            self.seen.discard(name)
            assert not isinstance(param_metas, NodeParamMeta)
            req_param = req_param_factory(
                name=name,
                alias=name,
                param_type=param_type,
                annotation=annotation,
                default=default,
                param_metas=param_metas,
                location="path",
            )
        elif self.is_lhl_primitive(param_type):
            plugin: ParsedParam[Any] = PluginParam(
                type_=param_type, annotation=annotation, name=name, default=default
            )
            return plugin
        elif is_body_param(param_type):
            if is_file_body(param_type):
                req_param = file_body_param(
                    name, param_type, annotation=annotation, default=default
                )
                req_param = cast(RequestParam[T], req_param)  # where T is UploadFile
            else:
                if param_metas and param_metas.custom_decoder:
                    decoder = param_metas.custom_decoder
                else:
                    decoder = decoder_factory(param_type)

                req_param = BodyParam(
                    name=name,
                    alias=name,
                    annotation=annotation,
                    type_=param_type,
                    default=default,
                    decoder=decoder,
                )
        elif param_type in self.graph.nodes:
            return self._parse_node(param_type)
        else:  # default case
            req_param = req_param_factory(
                name=name,
                alias=name,
                param_type=param_type,
                annotation=annotation,
                param_metas=param_metas,
                location="query",
                default=default,
            )
        return req_param

    def _parse_node(
        self, node_type: INode[..., Any], node_config: NodeConfig | None = None
    ) -> list[ParsedParam[Any]]:
        if node_config:
            node = self.graph.analyze(node_type, config=node_config)
        else:
            node = self.graph.analyze(node_type)

        params: list[Any | DependentNode] = [node]
        for dep_name, dep in node.dependencies.items():
            ptype, default = dep.param_type, dep.default_
            if default is IDIDI_MISSING:
                default = LIHIL_MISSING
            if ptype in self.graph.nodes:
                # only add top level dependency, leave subs to ididi
                continue
            ptype = cast(type, ptype)
            sub_params = self.parse_param(dep_name, ptype, default)
            params.extend(sub_params)
        return params

    def _parse_auth_header[T](
        self,
        name: str,
        header_key: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_metas: RequestParamMeta,
    ) -> ParsedParam[T]:
        # TODO: auth_header_decoder
        if JW_TOKEN_RETURN_MARK not in param_metas.metas:
            return req_param_factory(
                name=name,
                alias=header_key,
                param_type=type_,
                annotation=annotation,
                param_metas=param_metas,
                location="header",
                default=default,
            )
        else:
            if param_metas.custom_decoder:
                decoder = param_metas.custom_decoder
            else:
                if self.app_config is None or self.app_config.security is UNSET:
                    raise MissingDependencyError("security config")
                sec_config = self.app_config.security
                secret = sec_config.jwt_secret
                algos = sec_config.jwt_algorithms
                from lihil.auth.jwt import jwt_decoder_factory

                decoder = jwt_decoder_factory(
                    secret=secret, algorithms=algos, payload_type=type_
                )

            req_param = req_param_factory(
                name=name,
                alias=header_key,
                param_type=type_,
                annotation=annotation,
                decoder=decoder,
                location="header",
                default=default,
            )

        return req_param

    def _parse_header[T](
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_metas: RequestParamMeta,
    ) -> ParsedParam[T]:
        location = "header"
        pmetas = param_metas.metas
        mark_idx = pmetas.index(HEADER_REQUEST_MARK)
        key_meta = pmetas[mark_idx - 1]
        header_key = parse_header_key(name, key_meta).lower()

        if header_key == "authorization":
            return self._parse_auth_header(
                name=name,
                header_key=header_key,
                type_=type_,
                annotation=annotation,
                default=default,
                param_metas=param_metas,
            )
        else:
            param_alias = header_key

        return req_param_factory(
            name=name,
            alias=param_alias,
            param_type=type_,
            annotation=annotation,
            location=location,
            default=default,
            param_metas=param_metas,
        )

    def _parse_body[T](
        self,
        name: str,
        param_alias: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        mark_type: Literal["form", "body"],
        custom_decoder: IDecoder[Any, Any] | None,
    ) -> BodyParam[T]:
        if mark_type == "form":
            content_type = "multipart/form-data"
            decoder = custom_decoder or formdecoder_factory(type_)
            body_param = BodyParam(
                name=name,
                alias=param_alias,
                type_=type_,
                annotation=annotation,
                default=default,
                decoder=decoder,
                content_type=content_type,
            )
        else:
            decoder = custom_decoder or decoder_factory(type_)
            body_param = BodyParam(
                name=name,
                alias=param_alias,
                type_=type_,
                annotation=annotation,
                default=default,
                decoder=decoder,
            )
        return body_param

    def _parse_marked[T](
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_metas: RequestParamMeta,
    ) -> ParsedParam[T] | list[ParsedParam[T]]:
        custom_decoder = param_metas.custom_decoder
        mark_type = param_metas.mark_type
        assert mark_type

        if mark_type == "use":
            return self._parse_node(type_)
        else:
            # Easy case, Pure non-deps request params with param marks.
            location: ParamLocation
            param_alias = name

            if mark_type == "header":
                return self._parse_header(
                    name=name,
                    type_=type_,
                    annotation=annotation,
                    default=default,
                    param_metas=param_metas,
                )
            elif mark_type in ("body", "form"):
                return self._parse_body(
                    name,
                    param_alias=param_alias,
                    type_=type_,
                    annotation=annotation,
                    default=default,
                    mark_type=mark_type,
                    custom_decoder=custom_decoder,
                )

            elif mark_type == "path":
                location = "path"
            else:
                location = "query"

            req_param = req_param_factory(
                name=name,
                alias=param_alias,
                param_type=type_,
                annotation=annotation,
                location=location,
                default=default,
                param_metas=param_metas,
            )
            return req_param

    def _parse_plugin_from_meta(
        self,
        name: str,
        type_: RegularTypes,
        annotation: type[Any] | UnionType | GenericAlias | TypeAliasType,
        default: Maybe[Any],
        metas: list[Any] | None,
    ) -> list[ParsedParam[Any]] | None:
        if not metas:
            return None

        plugins: list[ParsedParam[Any]] = []
        for meta in metas:
            if isinstance(meta, PluginBase):
                plugin = meta.parse(name, type_, annotation, default)
                plugins.append(plugin)
            elif isinstance(meta, type) and issubclass(meta, PluginBase):
                raise NotSupportedError(f"Plugin {meta} is not Initialized")
            else:
                mark_type = extract_mark_type(meta)
                if mark_type:
                    if provider := PLUGIN_REGISTRY.get(mark_type):
                        plugin = provider.parse(name, type_, annotation, default)
                        plugins.append(plugin)
                    else:
                        NotSupportedError(
                            "Mixed param mark and plugins is not supported"
                        )
        return plugins if plugins else None

    def _parse_meta(
        self, metas: list[Any] | None
    ) -> RequestParamMeta | NodeParamMeta | None:
        if not metas:
            return None
        request_meta = RequestParamMeta(metas)
        for idx, meta in enumerate(metas):
            if isinstance(meta, CustomDecoder):
                request_meta.custom_decoder = meta.decode
            elif mark_type := extract_mark_type(meta):
                if request_meta.mark_type and request_meta.mark_type != mark_type:
                    raise NotSupportedError("can't use more than one param mark")
                request_meta.mark_type = mark_type
            elif meta == USE_FACTORY_MARK:
                factory, config = metas[idx + 1], metas[idx + 2]
                return NodeParamMeta(
                    metas=metas,
                    factory=factory,
                    node_config=config,
                )
            elif isinstance(meta, ParamConstraint):
                request_meta.constraint = meta
            else:
                continue
        return request_meta

    def parse_param[T](
        self,
        name: str,
        annotation: type[T] | UnionType | GenericAlias | TypeAliasType,
        default: Maybe[T] = LIHIL_MISSING,
    ) -> list[ParsedParam[T]]:
        parsed_type, pmetas = get_origin_pro(annotation)
        parsed_type = cast(type[T], parsed_type)

        if plugins := self._parse_plugin_from_meta(
            name, parsed_type, annotation, default, pmetas
        ):
            return plugins

        param_metas = self._parse_meta(pmetas)

        if isinstance(param_metas, NodeParamMeta):
            return self._parse_node(param_metas.factory, param_metas.node_config)

        if param_metas is None or not param_metas.mark_type:
            res = self._parse_rule_based(
                name=name,
                param_type=parsed_type,
                annotation=annotation,
                default=default,
                param_metas=param_metas,
            )
        else:
            res = self._parse_marked(
                name=name,
                type_=parsed_type,
                annotation=annotation,
                default=default,
                param_metas=param_metas,
            )
        return res if isinstance(res, list) else [res]

    def parse(
        self,
        f: ...,
        path_keys: tuple[str, ...] | None = None,
    ) -> "EndpointParams":
        func_params = tuple(signature(f).parameters.items())
        if path_keys:
            self.path_keys += path_keys

        params: dict[str, RequestParam[Any]] = {}
        bodies: dict[str, BodyParam[Any]] = {}
        nodes: dict[str, DependentNode] = {}
        plugins: dict[str, PluginParam] = {}

        for name, param in func_params:
            annotation, default = param.annotation, param.default
            if param.default is Parameter.empty:
                default = LIHIL_MISSING
            else:
                default = param.default
            parsed_params = self.parse_param(name, annotation, default)

            for req_param in parsed_params:
                if isinstance(req_param, DependentNode):
                    nodes[name] = req_param
                elif isinstance(req_param, PluginParam):
                    plugins[req_param.name] = req_param
                elif isinstance(req_param, BodyParam):
                    bodies[req_param.name] = req_param
                else:
                    params[req_param.name] = req_param

        if self.seen:
            warn(f"Unused path keys {self.seen}")

        return EndpointParams(
            params=params, bodies=bodies, nodes=nodes, plugins=plugins
        )
