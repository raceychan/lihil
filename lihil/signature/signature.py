from inspect import signature
from typing import Any, Awaitable, Callable

from ididi import DependentNode, Graph
from msgspec import Struct, field

from lihil.config import AppConfig
from lihil.interface import Base, IEncoder, Record
from lihil.problems import ValidationProblem
from lihil.utils.string import find_path_keys
from lihil.vendors import (
    FormData,
    Headers,
    QueryParams,
    Request,
    WebSocket,
    cookie_parser,
)

from .params import (
    BodyParam,
    CookieParam,
    HeaderParam,
    ParamParser,
    PathParam,
    PluginParam,
    QueryParam,
)
from .returns import EndpointReturn, parse_returns

type ParamMap[T] = dict[str, T]


def _is_form_body(param_pair: tuple[str, BodyParam[Any]] | None):
    if not param_pair:
        return False
    _, param = param_pair
    return param.content_type == "multipart/form-data" and param.type_ is not bytes


class ParseResult(Record):
    params: dict[str, Any]
    errors: list[ValidationProblem]

    callbacks: list[Callable[..., Awaitable[None]]] = field(default_factory=list)

    def __getitem__(self, key: str):
        return self.params[key]


class EndpointSignature[R](Base):
    route_path: str

    query_params: dict[str, QueryParam[Any]]
    path_params: dict[str, PathParam[Any]]
    header_params: dict[str, HeaderParam[Any]]

    body_param: tuple[str, BodyParam[Struct]] | None
    dependencies: ParamMap[DependentNode]
    plugins: ParamMap[PluginParam]

    default_status: int
    scoped: bool
    form_body: bool

    return_encoder: IEncoder[R]
    return_params: dict[int, EndpointReturn[R]]

    def override(self) -> None: ...

    def prepare_params(
        self,
        req_path: dict[str, str] | None = None,
        req_query: QueryParams | None = None,
        req_header: Headers | None = None,
        body: bytes | FormData | None = None,
    ) -> ParseResult:
        verrors: list[Any] = []
        params: dict[str, Any] = {}

        if req_header:
            raw_cookies: str | None = None
            cookie_params: dict[str, str] | None = None
            for name, param in self.header_params.items():
                if param.alias == "cookie":
                    cookie: CookieParam[Any] = param  # type: ignore

                    if raw_cookies is None:
                        raw_cookie = req_header["cookie"]
                    if cookie_params is None:
                        cookie_params = cookie_parser(raw_cookie)

                    raw_cookie: str = cookie_params[cookie.cookie_name]
                    val, error = param.validate(raw_cookie)
                else:
                    val, error = param.extract(req_header)

                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        zipped = (
            (req_path, self.path_params),
            (req_query, self.query_params),
        )

        for received, required in zipped:
            if received is None:
                continue
            received: Any
            for name, param in required.items():
                val, error = param.extract(received)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if self.body_param and body is not None:
            name, param = self.body_param
            val, error = param.extract(body)
            if val:
                params[name] = val
            else:
                verrors.append(error)

        parsed_result = ParseResult(params, verrors)
        return parsed_result

    def parse_query(self, req: Request | WebSocket) -> ParseResult:
        req_path = req.path_params if self.path_params else None
        req_query = req.query_params if self.query_params else None
        req_header = req.headers if self.header_params else None
        params = self.prepare_params(req_path, req_query, req_header, None)
        return params

    async def parse_command(self, req: Request) -> ParseResult:
        req_path = req.path_params if self.path_params else None
        req_query = req.query_params if self.query_params else None
        req_header = req.headers if self.header_params else None

        if self.form_body:
            body = await req.form()  # TODO: let user decide form configs
            params = self.prepare_params(req_path, req_query, req_header, body)
            params.callbacks.append(body.close)
        else:
            body = await req.body()
            params = self.prepare_params(req_path, req_query, req_header, body)
        return params

    @property
    def static(self) -> bool:
        return not any(
            (
                self.path_params,
                self.query_params,
                self.header_params,
                self.body_param,
                self.dependencies,
                self.plugins,
            )
        )

    @property
    def media_type(self) -> str:
        default = "application/json"
        return next(iter(self.return_params.values())).content_type or default

    @classmethod
    def from_function[FR](
        cls,
        graph: Graph,
        route_path: str,
        f: Callable[..., FR | Awaitable[FR]],
        app_config: AppConfig | None = None,
    ) -> "EndpointSignature[FR]":
        path_keys = find_path_keys(route_path)
        # Rename ParmaParser to FuncParser
        parser = ParamParser(graph, path_keys, app_config=app_config)
        params = parser.parse(f)
        # TODO: let ParamParser parse returns too
        return_params = parse_returns(
            signature(f).return_annotation, app_config=app_config
        )

        default_status = next(iter(return_params))
        default_encoder = return_params[default_status].encoder

        scoped = any(
            graph.should_be_scoped(node.dependent) for node in params.nodes.values()
        )

        body_param = params.get_body()
        form_body: bool = _is_form_body(body_param)

        info = EndpointSignature(
            route_path=route_path,
            header_params=params.get_location("header"),
            query_params=params.get_location("query"),
            path_params=params.get_location("path"),
            body_param=body_param,
            plugins=params.plugins,
            dependencies=params.nodes,
            return_params=return_params,
            default_status=default_status,
            return_encoder=default_encoder,
            scoped=scoped,
            form_body=form_body,
        )
        return info
