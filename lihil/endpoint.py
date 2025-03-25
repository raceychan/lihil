from inspect import isasyncgen, isgenerator
from typing import Any, Awaitable, Callable

from ididi import Graph
from ididi.graph import Resolver
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from lihil.config import EndPointConfig
from lihil.di import EndpointDeps, ParseResult, analyze_endpoint
from lihil.di.returns import agen_encode_wrapper, syncgen_encode_wrapper
from lihil.interface import HTTP_METHODS, IReceive, IScope, ISend
from lihil.plugins.bus import BusTerminal, EventBus
from lihil.problems import  InvalidRequestErrors, get_solver
from lihil.utils.threading import async_wrapper


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
        busterm: BusTerminal,
        config: EndPointConfig,
    ):
        self.path = path
        self.method = method
        self.tag = tag
        self.func = async_wrapper(func, threaded=config.to_thread)
        self.graph = graph
        self.busterm = busterm
        self.config = config

        self.name = func.__name__
        self.deps = analyze_endpoint(
            graph=self.graph, route_path=self.path, f=func, config=config
        )
        self.require_body: bool = self.deps.body_param is not None
        self.status_code = self.deps.default_status
        self.scoped: bool = self.deps.scoped
        self.encoder = self.deps.return_encoder

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.method}: {self.path!r} {self.func})"

    def inject_singletons(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ):
        for name, p in self.deps.singletons:
            ptype = p.type_
            if issubclass(ptype, Request):
                params[name] = request
            elif issubclass(ptype, EventBus):
                bus = self.busterm.create_event_bus(resolver)
                params[name] = bus
            elif issubclass(ptype, Resolver):
                params[name] = resolver

        return params

    async def make_call(
        self, scope: IScope, receive: IReceive, send: ISend, resolver: Resolver
    ) -> R | ParseResult | Response:
        request = Request(scope, receive, send)
        callbacks = None
        try:
            if self.require_body:
                parsed_result = await self.deps.parse_command(request)
            else:
                parsed_result = self.deps.parse_query(request)

            callbacks = parsed_result.callbacks

            if errors := parsed_result.errors:
                raise InvalidRequestErrors(detail=errors)

            params = self.inject_singletons(parsed_result.params, request, resolver)

            for name, dep in self.deps.dependencies:
                params[name] = await resolver.aresolve(dep.dependent, **params)

            raw_return = await self.func(**params)
            return raw_return
        except Exception as exc:
            if solver := get_solver(exc):
                return solver(request, exc)
            raise
        finally:
            if callbacks:
                for cb in callbacks:
                    await cb()

    def return_to_response(self, raw_return: Any) -> Response:
        if isinstance(raw_return, Response):
            resp = raw_return
        elif isgenerator(raw_return) or isasyncgen(raw_return):
            if isgenerator(raw_return) and not isasyncgen(raw_return):
                encode_wrapper = syncgen_encode_wrapper(raw_return, self.encoder)
            else:
                encode_wrapper = agen_encode_wrapper(raw_return, self.encoder)
            resp = StreamingResponse(
                encode_wrapper,
                media_type="text/event-stream",
                status_code=self.status_code,
            )
        else:
            resp = Response(
                content=self.encoder(raw_return), status_code=self.status_code
            )
        if (status := resp.status_code) < 200 or status in (204, 205, 304):
            resp.body = b""
        return resp

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if self.scoped:
            async with self.graph.ascope() as resolver:
                raw_return = await self.make_call(scope, receive, send, resolver)
                await self.return_to_response(raw_return)(scope, receive, send)
        else:
            raw_return = await self.make_call(scope, receive, send, self.graph)
            return await self.return_to_response(raw_return)(scope, receive, send)
