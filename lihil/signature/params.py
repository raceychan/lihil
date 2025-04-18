from copy import deepcopy
from inspect import Parameter, signature
from types import GenericAlias, UnionType
from typing import (
    Any,
    ClassVar,
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

from lihil.config import AppConfig
from lihil.errors import MissingDependencyError, NotSupportedError
from lihil.interface import MISSING as LIHIL_MISSING
from lihil.interface import (
    BodyContentType,
    CustomDecoder,
    Maybe,
    ParamLocation,
    RequestParamBase,
)
from lihil.interface.marks import (
    JW_TOKEN_RETURN_MARK,
    ParamMarkType,
    Struct,
    extract_mark_type,
)
from lihil.interface.struct import Base, IDecoder, IFormDecoder
from lihil.plugins.bus import EventBus
from lihil.plugins.registry import PLUGIN_REGISTRY, PluginBase, PluginParam
from lihil.utils.json import decoder_factory
from lihil.utils.string import parse_header_key
from lihil.utils.typing import (
    get_origin_pro,
    is_mapping_type,
    is_nontextual_sequence,
    is_union_type,
)
from lihil.vendor_types import FormData, Request, UploadFile

type ParsedParam[T] = PathParam[T] | PluginParam | BodyParam[T] | DependentNode


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

            return cast(IDecoder[str | list[str], T], str_to_bytes)  # here T is bytes

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
) -> "BodyParam[Any]":
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
) -> IFormDecoder[T] | IDecoder[bytes, T] | IDecoder[bytes, bytes]:

    def dummy_decoder(content: bytes) -> bytes:
        return content

    if not isinstance(ptype, type) or not issubclass(ptype, Struct):
        if ptype is bytes:
            return dummy_decoder

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


# TODO: we might support multiple decoders/encoders


# TODO: separate path param and (query, header param)

type RequestParam[T] = PathParam[T] | QueryParam[T]


class PathParam[T](RequestParamBase[T], kw_only=True):
    location: ClassVar[ParamLocation] = "path"
    decoder: IDecoder[str | list[str], T] = None  # type: ignore

    def __post_init__(self):
        super().__post_init__()

        if self.location == "path" and not self.required:
            raise NotSupportedError(
                f"Path param {self} with default value is not supported"
            )

        if cast(Any, self.decoder) is None:
            self.decoder = textdecoder_factory(self.type_)

    def __repr__(self) -> str:
        name_repr = (
            self.name if self.alias == self.name else f"{self.name!r}, {self.alias!r}"
        )
        return f"PathParam<{self.location}> ({name_repr}: {self.type_repr})"

    def decode(self, content: str | list[str]) -> T:
        """
        for decoder in self.decoders:
            contennt = decoder(content)
        """
        return self.decoder(content)


class QueryParam[T](RequestParamBase[T]):
    location: ClassVar[ParamLocation] = "query"
    decoder: IDecoder[str | list[str], T] = None  # type: ignore

    def __post_init__(self):
        super().__post_init__()

        if is_mapping_type(self.type_):
            raise NotSupportedError(
                f"query param should not be declared as mapping type, or a union that contains mapping type, received: {self.type_}"
            )

        if cast(Any, self.decoder) is None:
            self.decoder = textdecoder_factory(self.type_)

    def __repr__(self) -> str:
        name_repr = (
            self.name if self.alias == self.name else f"{self.name!r}, {self.alias!r}"
        )
        return f"PathParam<{self.location}> ({name_repr}: {self.type_repr})"

    def decode(self, content: str | list[str]) -> T:
        """
        for decoder in self.decoders:
            contennt = decoder(content)
        """
        return self.decoder(content)


class HeaderParam[T](QueryParam[T]):
    location: ClassVar[ParamLocation] = "header"


class BodyParam[T](RequestParamBase[T], kw_only=True):
    location: ClassVar[ParamLocation] = "body"
    decoder: IDecoder[bytes, T] | IFormDecoder[T]
    content_type: BodyContentType = "application/json"

    def __post_init__(self):
        super().__post_init__()
        assert self.location == "body"

    def __repr__(self) -> str:
        return f"BodyParam<{self.content_type}>({self.name}: {self.type_repr})"

    def decode(self, content: bytes | FormData) -> T:
        return self.decoder(content)  # type: ignore


class ParamMetas(Base):
    metas: tuple[Any, ...]

    custom_decoder: IDecoder[Any, Any] | None
    mark_type: ParamMarkType | None
    factory: INode[..., Any] | None = None
    node_config: NodeConfig | None = None

    @classmethod
    def from_metas(cls, metas: list[Any]) -> "ParamMetas":
        current_mark_type = None
        custom_decoder = None
        factory = None
        config = None

        for idx, meta in enumerate(metas):
            if isinstance(meta, CustomDecoder):
                custom_decoder = meta
            elif mark_type := extract_mark_type(meta):
                if current_mark_type and mark_type is not current_mark_type:
                    raise NotSupportedError("can't use more than one param mark")
                current_mark_type = mark_type
            elif meta == USE_FACTORY_MARK:  # TODO: use PluginParser
                factory, config = metas[idx + 1], metas[idx + 2]
            else:
                continue

        return ParamMetas(
            metas=tuple(metas),
            custom_decoder=custom_decoder.decode if custom_decoder else None,
            mark_type=current_mark_type,
            factory=factory,
            node_config=config,
        )


class EndpointParams(Base, kw_only=True):
    params: dict[str, PathParam[Any]] = field(default_factory=dict)
    bodies: dict[str, BodyParam[Any]] = field(default_factory=dict)
    nodes: dict[str, DependentNode] = field(default_factory=dict)
    plugins: dict[str, PluginParam] = field(default_factory=dict)

    def get_location(self, location: ParamLocation) -> dict[str, PathParam[Any]]:
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
    param_metas: ParamMetas | None = None,
    location: ParamLocation = "query",
) -> RequestParam[T]:
    if param_metas and param_metas.custom_decoder:
        decoder = param_metas.custom_decoder
    else:
        decoder = decoder or textdecoder_factory(param_type)

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
        self.plugin_types = LIHIL_DEPENDENCIES
        self.app_config = app_config

    def is_plugin_type(self, param_type: Any) -> TypeGuard[type]:
        "Dependencies that should be injected and managed by lihil"
        if not isinstance(param_type, type):
            param_origin = get_origin(param_type)
            if param_origin is Union:
                return any(self.is_plugin_type(arg) for arg in get_args(param_type))
            elif param_origin and is_builtin_type(param_origin):
                return False
            else:
                return self.is_plugin_type(type(param_type))
        else:
            return issubclass(param_type, self.plugin_types)

    def _parse_rule_based[T](
        self,
        name: str,
        param_type: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_metas: ParamMetas | None = None,
    ) -> ParsedParam[T] | list[ParsedParam[T]]:
        custom_decoder = None
        if param_metas and param_metas.custom_decoder:
            custom_decoder = param_metas.custom_decoder

        if name in self.path_keys:  # simplest case
            self.seen.discard(name)
            req_param = req_param_factory(
                name=name,
                alias=name,
                param_type=param_type,
                annotation=annotation,
                default=default,
                param_metas=param_metas,
                location="path",
            )
        elif self.is_plugin_type(param_type):
            return [
                PluginParam(
                    type_=param_type, annotation=annotation, name=name, default=default
                )
            ]
        elif is_body_param(param_type):
            if is_file_body(param_type):
                req_param = file_body_param(
                    name, param_type, annotation=annotation, default=default
                )
            else:
                decoder = custom_decoder or decoder_factory(param_type)
                req_param = BodyParam(
                    name=name,
                    alias=name,
                    annotation=annotation,
                    type_=param_type,
                    default=default,
                    decoder=decoder,
                )
        elif param_type in self.graph.nodes:
            node = self.graph.analyze(param_type)
            params: list[ParsedParam[Any]] = [node]
            for dep_name, dep in node.dependencies.items():
                ptype, dep_dfault = dep.param_type, dep.default_
                if dep_dfault is IDIDI_MISSING:
                    default = LIHIL_MISSING
                if ptype in self.graph.nodes:
                    # only add top level dependency, leave subs to ididi
                    continue
                ptype = cast(type, ptype)
                sub_params = self.parse_param(dep_name, ptype, default)
                params.extend(sub_params)
            return params
        elif param_metas and param_metas.factory:  # Annotated[Dep, use(dep_factory)]
            assert param_metas.node_config
            node = self.graph.analyze(
                param_metas.factory, config=param_metas.node_config
            )
            return self._parse_node(node)
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

    def _parse_node(self, node: DependentNode) -> list[ParsedParam[Any]]:
        params: list[Any | DependentNode] = [node]
        for dep_name, dep in node.dependencies.items():
            ptype, default = dep.param_type, dep.default_
            if default is IDIDI_MISSING:
                default = LIHIL_MISSING
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
        param_metas: ParamMetas,
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
            custom_decoder = param_metas.custom_decoder
            if custom_decoder is None:
                if self.app_config is None or self.app_config.security is None:
                    raise MissingDependencyError("security config")
                sec_config = self.app_config.security
                secret = sec_config.jwt_secret
                algos = sec_config.jwt_algorithms
                from lihil.auth.jwt import jwt_decoder_factory

                decoder = jwt_decoder_factory(
                    secret=secret, algorithms=algos, payload_type=type_
                )
            else:
                decoder = custom_decoder

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

    def _parse_marked[T](
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        param_metas: ParamMetas,
    ) -> ParsedParam[T] | list[ParsedParam[T]]:
        custom_decoder = (
            param_metas.custom_decoder if param_metas.custom_decoder else None
        )
        mark_type = param_metas.mark_type

        if mark_type == "use":
            node = self.graph.analyze(type_)
            return self._parse_node(node)
        else:
            # Easy case, Pure non-deps request params with param marks.
            location: ParamLocation
            param_alias = name
            content_type: BodyContentType = "application/json"

            if mark_type == "header":
                location = "header"
                header_key = parse_header_key(name, param_metas.metas).lower()
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
            elif mark_type == "body":
                decoder = custom_decoder or decoder_factory(type_)
                body_param = BodyParam(
                    name=name,
                    alias=param_alias,
                    type_=type_,
                    annotation=annotation,
                    default=default,
                    decoder=decoder,
                    content_type=content_type,
                )
                return body_param
            elif mark_type == "form":
                content_type = "multipart/form-data"
                decoder = custom_decoder or formdecoder_factory(type_)
                body_param = BodyParam(
                    name=name,
                    alias=param_alias,
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
        type_: type | UnionType,
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

    def parse_param[T](
        self,
        name: str,
        annotation: type[T] | UnionType | GenericAlias | TypeAliasType,
        default: Maybe[T] = LIHIL_MISSING,
    ) -> list[ParsedParam[T]]:
        parsed_type, pmetas = get_origin_pro(annotation)

        if plugins := self._parse_plugin_from_meta(
            name, parsed_type, annotation, default, pmetas
        ):
            return plugins

        param_metas = ParamMetas.from_metas(pmetas) if pmetas else None
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

        params = dict[str, PathParam[Any]]()
        bodies = dict[str, BodyParam[Any]]()
        nodes = dict[str, DependentNode]()
        plugins = dict[str, PluginParam]()

        for name, param in func_params:
            annotation, default = param.annotation, param.default
            default = (
                LIHIL_MISSING if param.default is Parameter.empty else param.default
            )
            parsed_params = self.parse_param(name, annotation, default)

            for req_param in parsed_params:
                if isinstance(req_param, DependentNode):
                    nodes[name] = req_param
                    continue
                if isinstance(req_param, PluginParam):
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
