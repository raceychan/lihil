from inspect import signature
from typing import Any, Awaitable, Callable, Mapping

from ididi import DependentNode, Graph
from msgspec import DecodeError, Struct, ValidationError, field

from lihil.config import AppConfig
from lihil.interface import Base, IEncoder, Record, is_provided
from lihil.problems import (
    CustomDecodeErrorMessage,
    CustomValidationError,
    InvalidDataType,
    InvalidJsonReceived,
    MissingRequestParam,
    ValidationProblem,
)
from lihil.utils.string import find_path_keys
from lihil.utils.typing import is_nontextual_sequence
from lihil.vendor_types import FormData, Headers, QueryParams, Request

from .params import ParamParser, PluginParam, BodyParam, RequestParam
from .returns import EndpointReturn, parse_returns

type ParamMap[T] = dict[str, T]
type RequestParamMap = dict[str, RequestParam[Any]]


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


def _validate_param[T](
    name: str,
    alias: str,
    raw_val: str | list[str] | None,
    param: RequestParam[T],
) -> tuple[T, None] | tuple[None, ValidationProblem]:
    if raw_val is None:
        if is_provided(param.default):
            return param.default, None
        else:
            return (None, MissingRequestParam(param.location, alias))
    else:
        try:
            value = param.decode(raw_val)
            return value, None
        except ValidationError as mve:
            error = InvalidDataType(param.location, name, str(mve))
        except DecodeError:
            error = InvalidJsonReceived(param.location, name)
        except CustomValidationError as cve:  # type: ignore
            error = CustomDecodeErrorMessage(param.location, name, cve.detail)
        return None, error


def _validate_body[T](
    name: str, raw_val: bytes | FormData, param: BodyParam[T]
) -> tuple[T, None] | tuple[None, ValidationProblem]:
    try:
        value = param.decode(raw_val)
        return value, None
    except ValidationError as mve:
        error = InvalidDataType(param.location, name, str(mve))
    except DecodeError:
        error = InvalidJsonReceived(param.location, name)
    except CustomValidationError as cve:  # type: ignore
        error = CustomDecodeErrorMessage(param.location, name, cve.detail)
    return None, error


class EndpointSignature[R](Base):
    route_path: str

    query_params: RequestParamMap
    path_params: RequestParamMap
    header_params: RequestParamMap
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
        req_path: Mapping[str, Any] | None = None,
        req_query: QueryParams | None = None,
        req_header: Headers | None = None,
        body: bytes | FormData | None = None,
    ) -> ParseResult:
        verrors: list[Any] = []
        params: dict[str, Any] = {}

        if req_header:
            for name, param in self.header_params.items():
                alias = param.alias
                ptype = param.type_
                if is_nontextual_sequence(ptype):
                    raw = req_header.getlist(alias)
                else:
                    raw = req_header.get(alias)

                val, error = _validate_param(name, alias, raw, param)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if req_path:
            for name, param in self.path_params.items():
                alias = param.alias
                raw = req_path.get(alias)
                val, error = _validate_param(name, alias, raw, param)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if req_query:
            for name, param in self.query_params.items():
                alias = param.alias
                ptype = param.type_

                if is_nontextual_sequence(ptype):
                    raw = req_query.getlist(alias)
                else:
                    raw = req_query.get(alias)

                val, error = _validate_param(name, alias, raw, param)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if self.body_param and body is not None:
            name, param = self.body_param
            val, error = None, None

            if body == b"" or (isinstance(body, FormData) and len(body) == 0):
                if is_provided(param.default):
                    val = param.default
                else:
                    error = MissingRequestParam(param.location, name)
            else:
                val, error = _validate_body(name, body, param)

            if val:
                params[name] = val
            else:
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
            body = await req.form()  # TODO: let user decide form configs
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
        app_config: AppConfig | None = None,
    ) -> "EndpointSignature[FR]":
        path_keys = find_path_keys(route_path)

        parser = ParamParser(graph, path_keys, app_config=app_config)
        params = parser.parse(f, path_keys)
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
