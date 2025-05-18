from inspect import iscoroutinefunction
from typing import Any

from ididi import Graph, Resolver
from starlette.responses import Response
from typing_extensions import Unpack

from lihil.errors import NotSupportedError
from lihil.interface import ASGIApp, Func, IReceive, IScope, ISend
from lihil.routing import EndpointProps, IEndpointProps, RouteBase, build_path_regex
from lihil.signature import EndpointParser, EndpointSignature, Injector, ParseResult
from lihil.vendors import WebSocket


class WebSocketEndpoint:  # TODO:  endpoint base
    def __init__(
        self, route: "WebSocketRoute", func: Func[..., None], props: EndpointProps
    ):
        self._route = route
        self._unwrapped_func = func
        if not iscoroutinefunction(func):
            raise NotSupportedError("sync function is not supported for websocket")
        self._func = func
        self._name = func.__name__
        self._props = props

    @property
    def unwrapped_func(self):
        return self._unwrapped_func

    async def setup(self, sig: EndpointSignature[None]) -> None:
        self._graph = self._route.graph
        self._sig = sig
        for decor in self._props.plugins:
            self._func = await decor(self._graph, self._func, sig)
        self._injector = Injector(self._sig)
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
            parsed = await self._injector.validate_websocket(ws, resolver)
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

    async def setup(self, graph: Graph | None = None):
        if self.endpoint is None:
            raise RuntimeError(f"Empty websocket route")

        await super().setup(graph=graph)
        self.endpoint_parser = EndpointParser(self.graph, self.path)
        sig = self.endpoint_parser.parse(self.endpoint.unwrapped_func)
        if sig.body_param is not None:
            raise NotSupportedError(
                f"Websocket does not support body param, got {sig.body_param}"
            )
        await self.endpoint.setup(sig)
        self.call_stack = self.chainup_middlewares(self.endpoint)

    def ws_handler(self, func: Any = None, **iprops: Unpack[IEndpointProps]) -> Any:
        props = EndpointProps.from_unpack(**iprops)
        endpoint = WebSocketEndpoint(self, func=func, props=props)

        self.endpoint = endpoint
        if self.path_regex is None:
            self.path_regex = build_path_regex(self.path)
        return func
