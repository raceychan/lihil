from inspect import signature
from typing import Any, Awaitable, Callable, Mapping

from ididi import DependentNode, Graph
from msgspec import DecodeError, Struct, ValidationError, field
from starlette.requests import Request

from lihil.di.params import ParamParser, PluginParam, RequestBodyParam, RequestParam
from lihil.di.returns import EndpointReturn, parse_returns  # pparse_returns,
from lihil.interface import MISSING, Base, IEncoder, Record, is_provided
from lihil.problems import (
    InvalidDataType,
    InvalidJsonReceived,
    MissingRequestParam,
    ValidationProblem,
)
from lihil.utils.parse import find_path_keys
from lihil.vendor_types import FormData

type ParamMap[T] = dict[str, T]
type RequestParamMap = dict[str, RequestParam[Any]]


def is_form_body(param_pair: tuple[str, RequestBodyParam[Any]] | None):
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

    @property
    def require_callback(self):
        return bool(self.callbacks)


# TODO: separate param parsing and dependency injection
class EndpointDeps[R](Base):
    route_path: str

    query_params: RequestParamMap
    path_params: RequestParamMap
    header_params: RequestParamMap
    body_param: tuple[str, RequestBodyParam[Struct]] | None
    dependencies: ParamMap[DependentNode]
    plugins: ParamMap[PluginParam[Any]]

    default_status: int
    scoped: bool
    form_body: bool

    return_encoder: IEncoder[R]
    return_params: dict[int, EndpointReturn[R]]

    def override(self) -> None: ...

    # TODO:we shou rewrite this in cython, along with the request object
    def prepare_params(
        self,
        req_path: Mapping[str, Any] | None = None,
        req_query: Mapping[str, Any] | None = None,
        req_header: Mapping[str, Any] | None = None,
        body: bytes | FormData | None = None,
    ) -> ParseResult:
        verrors: list[Any] = []
        params: dict[str, Any] = {}

        zipped = (
            (self.path_params, req_path),
            (self.query_params, req_query),
            (self.header_params, req_header),
        )

        for required, received in zipped:
            if received is None:
                continue

            for name, param in required.items():
                alias = param.alias if param.alias else param.name
                if (val := received.get(alias, MISSING)) is not MISSING:
                    val = received[alias]

                    try:
                        params[name] = param.decode(val)
                    except ValidationError as mve:
                        error = InvalidDataType(param.location, name, str(mve))
                        verrors.append(error)
                    except DecodeError:
                        error = InvalidJsonReceived(param.location, name)
                        verrors.append(error)
                elif not param.required:
                    params[name] = param.default
                else:
                    err = MissingRequestParam(param.location, name)
                    verrors.append(err)

        if self.body_param and body is not None:
            name, param = self.body_param
            if body == b"":  # empty bytes body
                if is_provided(param.default):
                    body = param.default  # TODO: is_provided
                else:
                    err = MissingRequestParam("body", name)
                    verrors.append(err)
            elif isinstance(body, FormData) and len(body) == 0:  # empty form body
                if is_provided(param.default):
                    body = param.default
                else:
                    err = MissingRequestParam("body", name)
                    verrors.append(err)
            else:
                try:
                    params[name] = param.decode(body)
                except ValidationError as mve:
                    error = InvalidDataType("body", name, str(mve))
                    verrors.append(error)
                except DecodeError:
                    error = InvalidJsonReceived("body", name)
                    verrors.append(error)

        parsed_result = ParseResult(params, verrors)
        return parsed_result

    def parse_query(self, req: Request) -> ParseResult:
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
            body = await req.form()
            params = self.prepare_params(req_path, req_query, req_header, body)
            params.callbacks.append(body.close)
        else:
            body = await req.body()
            params = self.prepare_params(req_path, req_query, req_header, body)
        return params

    @classmethod
    def from_function[FR](
        cls,
        graph: Graph,
        route_path: str,
        f: Callable[..., FR | Awaitable[FR]],
    ) -> "EndpointDeps[FR]":
        path_keys = find_path_keys(route_path)
        func_sig = signature(f)
        func_params = tuple(func_sig.parameters.items())

        parser = ParamParser(graph, path_keys)
        params = parser.parse(func_params, path_keys)
        return_params = parse_returns(func_sig.return_annotation)

        default_status = next(iter(return_params))
        default_encoder = return_params[default_status].encoder

        scoped = any(
            graph.should_be_scoped(node.dependent) for node in params.nodes.values()
        )

        body_param = params.get_body()
        form_body: bool = is_form_body(body_param)

        info = EndpointDeps(
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
