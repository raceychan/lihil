from concurrent.futures import ThreadPoolExecutor
from inspect import iscoroutinefunction
from typing import Any, Awaitable, Callable

from ididi import Graph, Resolver
from starlette.responses import Response
from typing_extensions import Self, Unpack

from lihil.errors import NotSupportedError
from lihil.interface import ASGIApp, Func, IReceive, IScope, ISend
from lihil.routing import EndpointInfo, EndpointProps, IEndpointProps, RouteBase
from lihil.signature import EndpointParser, EndpointSignature, Injector, ParseResult
from lihil.utils.string import merge_path
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

    @property
    def props(self):
        return self._props

    def chainup_plugins(
        self, func: Callable[..., Awaitable[None]], sig: EndpointSignature[None]
    ) -> Callable[..., Awaitable[None]]:
        seen: set[int] = set()
        for decor in self._props.plugins:
            if (decor_id := id(decor)) in seen:
                continue

            ep_info = EndpointInfo(self._route.graph, func, sig)
            func = decor(ep_info)
            seen.add(decor_id)
        return func

    def setup(self, sig: EndpointSignature[None]) -> None:
        self._graph = self._route.graph
        self._sig = sig
        self._func = self.chainup_plugins(self._func, sig)
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
            raise RuntimeError(f"{self.__class__.__name__}({self._path}) not setup")
        await self.call_stack(scope, receive, send)

    def __repr__(self):
        return f"{self.__class__.__name__}({self._path!r}, {self.endpoint})"

    def _setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ):
        if self.endpoint is None:
            raise RuntimeError(f"Empty websocket route")

        super()._setup(graph=graph, workers=workers)
        self.endpoint_parser = EndpointParser(self._graph, self._path)
        sig = self.endpoint_parser.parse(self.endpoint.unwrapped_func)
        if sig.body_param is not None:
            raise NotSupportedError(
                f"Websocket does not support body param, got {sig.body_param}"
            )
        self.endpoint.setup(sig)
        self.call_stack = self.chainup_middlewares(self.endpoint)

    def include_subroutes(self, *subs: Self, parent_prefix: str | None = None) -> None:
        """
        Merge other routes into current route as sub routes,
        a new route would be created based on the merged subroute

        NOTE: This method is NOT idempotent
        """
        for sub in subs:
            self._graph.merge(sub._graph)
            if parent_prefix:
                sub_path = sub._path.removeprefix(parent_prefix)
            else:
                sub_path = sub._path
            merged_path = merge_path(self._path, sub_path)
            sub_subs = sub._subroutes
            new_sub = self.__class__(
                path=merged_path,
                graph=self._graph,
                middlewares=sub.middle_factories,
            )
            if sub.endpoint is not None:
                new_sub.ws_handler(sub.endpoint.unwrapped_func, **sub.endpoint.props)

            for sub_sub in sub_subs:
                new_sub.include_subroutes(sub_sub, parent_prefix=sub._path)
            self._subroutes.append(new_sub)

    def ws_handler(self, func: Any = None, **iprops: Unpack[IEndpointProps]) -> Any:
        props = EndpointProps.from_unpack(**iprops)
        endpoint = WebSocketEndpoint(self, func=func, props=props)

        self.endpoint = endpoint
        return func
