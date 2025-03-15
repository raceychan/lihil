from inspect import signature
from typing import Any, Awaitable, Callable, Mapping, Self, Sequence, cast
from warnings import warn

from ididi import DependentNode, Graph
from msgspec import DecodeError, ValidationError
from starlette.requests import Request

from lihil.di.params import RequestParam, SingletonParam, analyze_request_params
from lihil.di.returns import ReturnParam, analyze_return
from lihil.interface import MISSING, Base, Record
from lihil.problems import (
    InvalidDataType,
    InvalidJsonReceived,
    MissingRequestParam,
    ValidationProblem,
)
from lihil.utils.parse import find_path_keys

type ParamPair = tuple[str, RequestParam[Any]]
type RequiredParams = Sequence[ParamPair]


class ParseResult(Record):
    params: dict[str, Any]
    errors: list[ValidationProblem]

    def __getitem__(self, key: str):
        return self.params[key]

    def __ior__(self, other: "ParseResult") -> Self:
        self.params.update(other.params)
        self.errors.extend(other.errors)
        return self


class EndpointDeps[R](Base):
    route_path: str

    query_params: RequiredParams
    path_params: RequiredParams
    header_params: RequiredParams
    body_param: ParamPair | None
    dependencies: tuple[tuple[str, DependentNode], ...]
    singletons: tuple[tuple[str, SingletonParam[Any]], ...]

    return_param: ReturnParam[R]  # | UnionType
    scoped: bool

    def override(self) -> None:
        raise NotImplementedError

    @property
    def default_status(self) -> int:
        return self.return_param.status

    # TODO:we shou rewrite this in cython, along with the request object
    def prepare_params(
        self,
        req_path: Mapping[str, Any] | None = None,
        req_query: Mapping[str, Any] | None = None,
        req_header: Mapping[str, Any] | None = None,
        body: Any | None = None,
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

            for name, param in required:
                alias = param.alias if param.alias else param.name
                if (val := received.get(alias, MISSING)) is not MISSING:
                    val = received[alias]

                    try:
                        params[name] = param.decoder(val)
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
            if body == b"":  # empty bytes
                if not param.required:
                    body = param.default
                else:
                    err = MissingRequestParam("body", name)
                    verrors.append(err)
            else:
                try:
                    params[name] = param.decoder(body)
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
        body = await req.body()
        params = self.prepare_params(req_path, req_query, req_header, body)
        return params


def analyze_endpoint[R](
    graph: Graph, route_path: str, f: Callable[..., R | Awaitable[R]]
) -> "EndpointDeps[R]":
    path_keys = find_path_keys(route_path)
    seen_path: set[str] = set(path_keys)
    func_sig = signature(f)
    func_params = tuple(func_sig.parameters.items())
    params = analyze_request_params(func_params, graph, seen_path, path_keys)
    retparam = analyze_return(func_sig.return_annotation)
    if seen_path:
        warn(f"Unused path keys {seen_path}")
    scoped = any(graph.should_be_scoped(node.dependent) for _, node in params.nodes)
    info = EndpointDeps(
        route_path=route_path,
        header_params=params.get_location("header"),
        query_params=params.get_location("query"),
        path_params=params.get_location("path"),
        body_param=params.get_body(),
        singletons=tuple(params.singletons),
        dependencies=tuple(params.nodes),
        return_param=cast(ReturnParam[R], retparam),
        scoped=scoped,
    )
    return info
