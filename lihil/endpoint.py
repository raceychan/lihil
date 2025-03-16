from asyncio import to_thread
from inspect import isasyncgen, iscoroutinefunction, isgenerator
from typing import Any, Awaitable, Callable, Sequence, TypedDict, Unpack

from ididi import Graph
from ididi.graph import Resolver
from msgspec import field
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from lihil.di import EndpointDeps, ParseResult, analyze_endpoint
from lihil.di.returns import agen_encode_wrapper, syncgen_encode_wrapper
from lihil.interface import HTTP_METHODS, FlatRecord, IReceive, IScope, ISend
from lihil.plugins.bus import EventBus
from lihil.problems import DetailBase, InvalidRequestErrors, get_solver


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


class IEndPointConfig(TypedDict, total=False):
    errors: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
    in_schema: bool
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
        busmaker: Callable[[Resolver], EventBus],
        config: EndPointConfig,
    ):
        self.path = path
        self.method = method
        self.tag = tag
        self.func = async_wrapper(func, config.to_thread)
        self.graph = graph
        self.busmaker = busmaker
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
        try:
            if self.require_body:
                parsed_result = await self.deps.parse_command(request)
            else:
                parsed_result = self.deps.parse_query(request)

            if errors := parsed_result.errors:
                raise InvalidRequestErrors(detail=errors)

            params = parsed_result.params
            for name, p in self.deps.singletons:
                if p.type_ is Request:
                    params[name] = request
                    # TODO: message bus
                elif p.type_ is EventBus:
                    bus = self.busmaker(resolver)
                    params[name] = bus
                else:
                    raise NotImplementedError(f"unhandle lihil deps {p.type_}")

            for name, dep in self.deps.dependencies:
                params[name] = await resolver.aresolve(dep.dependent, **params)

            raw_return = await self.func(**params)
            return raw_return
        except Exception as exc:
            if solver := get_solver(exc):
                return solver(request, exc)
            raise

    def parse_raw_return(self, scope: IScope, raw_return: Any) -> Response:
        # TODO:
        # self.deps.return_param.generate_response
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
            # TODO: this should be done in the server layer
            resp.body = b""
        return resp

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if self.scoped:
            async with self.graph.ascope() as resolver:
                raw_return = await self.make_call(scope, receive, send, resolver)
                await self.parse_raw_return(scope, raw_return)(scope, receive, send)
        else:
            raw_return = await self.make_call(scope, receive, send, self.graph)
            await self.parse_raw_return(scope, raw_return)(scope, receive, send)
