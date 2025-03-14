from asyncio import to_thread
from inspect import isasyncgen, iscoroutinefunction, isgenerator
from typing import Any, Awaitable, Callable, Sequence, Unpack

from ididi import Graph
from ididi.graph import Resolver
from msgspec import field
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from lihil.constant.status import STATUS_CODE, UNPROCESSABLE_ENTITY
from lihil.di import EndpointDeps, ParseResult, analyze_endpoint
from lihil.interface import HTTP_METHODS, FlatRecord, IReceive, IScope, ISend
from lihil.oas.model import IOASConfig  # , OASConfig
from lihil.problems import DetailBase, ErrorResponse, InvalidRequestErrors, get_solver


def async_wrapper[R](
    func: Callable[..., R], threaded: bool = True
) -> Callable[..., Awaitable[R]]:
    # TODO: use our own Threading workers
    if iscoroutinefunction(func):
        return func

    async def inner(**params: Any) -> R:
        return await to_thread(func, **params)

    async def dummy(**params: Any) -> R:
        return func(**params)

    return inner if threaded else dummy


class IEndPointConfig(IOASConfig, total=False):
    to_thread: bool


class EndPointConfig(FlatRecord, kw_only=True):
    """
    # TODO: implement this through ep decorator
    [tool.lihil.oas]
    "/users/{user_id}" = { include_schema = true }
    """

    errors: tuple[type[DetailBase[Any]], ...] = field(default_factory=tuple)
    to_thread: bool = True
    in_schema: bool = True

    @classmethod
    def from_unpack(cls, **iconfig: Unpack[IEndPointConfig]):
        if raw_errors := iconfig.get("errors"):
            if not isinstance(raw_errors, Sequence):
                errors = (raw_errors,)
            else:
                errors = tuple(raw_errors)

            iconfig["errors"] = errors

        return cls(**iconfig)  # type: ignore


class Endpoint[R]:
    method: HTTP_METHODS
    path: str
    tag: str
    name: str
    func: Callable[..., Awaitable[R]]
    graph: Graph
    deps: EndpointDeps[R]
    status_code: int

    def __init__(
        self,
        path: str,
        method: HTTP_METHODS,
        tag: str,
        func: Callable[..., R],
        graph: Graph,
        config: EndPointConfig,
    ):
        self.path = path
        self.method = method
        self.tag = tag
        self.func = async_wrapper(func, config.to_thread)
        self.graph = graph
        self.config = config

        self.name = func.__name__
        self.deps = analyze_endpoint(graph=self.graph, route_path=self.path, f=func)
        self.require_body: bool = self.deps.body_param is not None
        self.status_code = self.deps.return_param.status
        self.scoped: bool = self.deps.scoped
        self.encoder = self.deps.return_param.encoder

    def override(self, **deps: Any) -> None:
        # TODO: support endpoint-specific dependencies override
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.method}: {self.path!r} {self.func})"

    async def make_call(
        self, scope: IScope, receive: IReceive, send: ISend, resolver: Resolver
    ) -> R | ParseResult | Response:
        request = Request(scope, receive, send)

        # TODO: problem solver
        try:
            if self.require_body:
                parsed_result = await self.deps.parse_command(request)
            else:
                parsed_result = self.deps.parse_query(request)

            if parsed_result.errors:
                return parsed_result

            params = parsed_result.params
            for name, p in self.deps.singletons:
                if p.type_ is Request:
                    params[name] = request
                # Todo: message bus
                else:
                    raise NotImplementedError

            for name, dep in self.deps.dependencies:
                params[name] = await resolver.aresolve(dep.dependent, **params)

            raw_return = await self.func(**params)
            return raw_return
        except Exception as exc:
            solver = get_solver(exc)
            if not solver:
                raise
            return solver(request, exc)

    def parse_raw_return(self, scope: IScope, raw_return: Any) -> Response:
        # TODO: if status < 200 or is 204, 205, 304, drop body, we should leave this to our server
        if isinstance(raw_return, Response):
            resp = raw_return
        elif isinstance(raw_return, ParseResult):
            # TODO: we might make InvalidRequestErrors an exception so that user can catch it
            errors = InvalidRequestErrors(detail=raw_return.errors)
            detail = errors.__problem_detail__(scope["path"])
            resp = ErrorResponse(detail, status_code=STATUS_CODE[UNPROCESSABLE_ENTITY])
        elif isgenerator(raw_return) or isasyncgen(raw_return):
            # TODO: check generator here
            return StreamingResponse(
                raw_return, media_type="text/event-stream", status_code=self.status_code
            )
        else:
            resp = Response(
                content=self.encoder(raw_return), status_code=self.status_code
            )
        return resp

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if self.scoped:
            async with self.graph.ascope() as resolver:
                raw_return = await self.make_call(scope, receive, send, resolver)
                await self.parse_raw_return(scope, raw_return)(scope, receive, send)
        else:
            raw_return = await self.make_call(scope, receive, send, self.graph)
            await self.parse_raw_return(scope, raw_return)(scope, receive, send)

    @classmethod
    def from_func(
        cls, func: Callable[..., R], graph: Graph, **iconfig: Unpack[IEndPointConfig]
    ) -> "Endpoint[R]":
        "A test helper"
        config = EndPointConfig.from_unpack(**iconfig) if iconfig else EndPointConfig()
        return cls(path="", method="GET", tag="", func=func, graph=graph, config=config)
