from inspect import iscoroutinefunction
from typing import Any

from ididi import Graph, Resolver
from starlette.responses import Response

from lihil.errors import NotSupportedError
from lihil.interface import ASGIApp, Func, IReceive, IScope, ISend
from lihil.plugins.bus import BusTerminal
from lihil.routing import RouteBase, build_path_regex
from lihil.signature import EndpointParser, ParseResult
from lihil.vendors import WebSocket


class WebSocketEndpoint:  # TODO:  endpoint base
    def __init__(self, route: "WebSocketRoute", func: Func[..., None]):
        self._route = route
        self._unwrapped_func = func
        if not iscoroutinefunction(func):
            raise NotSupportedError("sync function is not supported for websocket")
        self._func = func
        self._name = func.__name__

    def setup(self) -> None:
        self._graph = self._route.graph
        self._busterm = self._route.busterm
        self._sig = self._route.endpoint_parser.parse(self._unwrapped_func)

        if self._sig.body_param is not None:
            raise NotSupportedError("websocket does not support body param")

        self._scoped: bool = self._sig.scoped

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._route.path!r} {self._func})"

    async def make_call(
        self,
        scope: IScope,
        receive: IReceive,
        send: ISend,
        resolver: Resolver,
    ) -> None | ParseResult | Response:
        ws = WebSocket(scope, receive, send)

        try:
            parsed = await self._sig.validate_websocket(ws, resolver, self._busterm)
            await self._func(**parsed.params)
        except Exception as exc:
            await ws.close(reason=str(exc))
            raise

    async def __call__(
        self,
        scope: IScope,
        receive: IReceive,
        send: ISend,
    ) -> None:
        if self._scoped:
            async with self._graph.ascope() as resolver:
                await self.make_call(scope, receive, send, resolver)
        else:
            await self.make_call(scope, receive, send, self._graph)


class WebSocketRoute(RouteBase):
    endpoint: WebSocketEndpoint | None = None
    call_stack: ASGIApp | None = None

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if not self.call_stack:
            raise RuntimeError(f"{self.__class__.__name__}({self.path}) not setup")
        await self.call_stack(scope, receive, send)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.path!r}, {self.endpoint})"

    def setup(self, graph: Graph | None = None, busterm: BusTerminal | None = None):
        super().setup(graph=graph, busterm=busterm)
        self.endpoint_parser = EndpointParser(self.graph, self.path)

        if self.endpoint is None:
            raise RuntimeError(f"Empty websocket route")

        self.endpoint.setup()
        self.call_stack = self.chainup_middlewares(self.endpoint)

    def ws_handler(self, func: Any = None) -> Any:
        endpoint = WebSocketEndpoint(self, func=func)

        self.endpoint = endpoint
        if self.path_regex is None:
            self.path_regex = build_path_regex(self.path)
        return func
