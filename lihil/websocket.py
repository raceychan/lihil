import warnings
from concurrent.futures import ThreadPoolExecutor
from inspect import iscoroutinefunction
from typing import Any

from ididi import Graph, Resolver
from typing_extensions import Self, Unpack

from lihil.errors import NotSupportedError
from lihil.interface import (
    ASGIApp,
    Func,
    IAsyncFunc,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    R,
)
from lihil.problems import InvalidRequestErrors
from lihil.routing import EndpointInfo, EndpointProps, IEndpointProps, RouteBase
from lihil.signature import EndpointParser, EndpointSignature, Injector, ParseResult
from lihil.utils.string import merge_path
from lihil.vendors import Response, WebSocket, WebSocketDisconnect, WebSocketState


class WebSocketInjector(Injector[R]):
    async def validate_websocket(self, socket: WebSocket, resolver: Resolver):
        parsed_result = self._validate_conn(socket)

        if errors := parsed_result.errors:
            raise InvalidRequestErrors(detail=errors)

        params = parsed_result.params
        for name, p in self.state_params:
            ptype = p.type_
            if not isinstance(ptype, type):
                continue
            elif issubclass(ptype, WebSocket):
                params[name] = socket
            elif issubclass(ptype, Resolver):
                params[name] = resolver

        for name, dep in self.deps:
            params[name] = await resolver.aresolve(dep.dependent, **params)

        for p in self.transitive_params:
            params.pop(p)
        return parsed_result


class WebSocketEndpoint:
    def __init__(
        self,
        path: str,
        func: Func[..., None],
        props: EndpointProps,
    ):
        self._path = path
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
        self,
        func: IAsyncFunc[..., None],
        sig: EndpointSignature[None],
        graph: Graph,
    ) -> IAsyncFunc[..., None]:
        seen: set[int] = set()
        for decor in self._props.plugins:
            if (decor_id := id(decor)) in seen:
                continue

            ep_info = EndpointInfo(graph, func, sig)
            func = decor(ep_info)
            seen.add(decor_id)
        return func

    def setup(self, sig: EndpointSignature[None], graph: Graph) -> None:
        self._graph = graph
        self._sig = sig
        self._func = self.chainup_plugins(self._func, sig, graph)
        self._injector = WebSocketInjector(self._sig)
        self._scoped: bool = self._sig.scoped

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._path!r} {self._func})"

    async def make_call(
        self,
        scope: IScope,
        receive: IReceive,
        send: ISend,
        resolver: Resolver,
    ) -> None | ParseResult | Response:
        sock = WebSocket(scope, receive, send)

        try:
            parsed = await self._injector.validate_websocket(sock, resolver)
            await self._func(**parsed.params)
        except WebSocketDisconnect:
            # we should not send close message when client is disconnected already
            return
        except Exception:
            if sock.client_state == WebSocketState.CONNECTED:
                await sock.close(code=1011, reason="Internal Server Error")
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
    call_stack: ASGIApp | None = None

    def __init__(
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
    ):
        super().__init__(path, graph=graph, middlewares=middlewares)
        self._ws_ep: WebSocketEndpoint | None = None

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if not self.call_stack:
            raise RuntimeError(f"{self.__class__.__name__}({self._path}) not setup")
        await self.call_stack(scope, receive, send)

    def __repr__(self):
        return f"{self.__class__.__name__}({self._path!r}, {self._ws_ep})"

    def setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ):
        if self._ws_ep is None:
            raise RuntimeError(f"Empty {self} without any registered endpoint")

        super().setup(graph=graph, workers=workers)
        self.endpoint_parser = EndpointParser(self._graph, self._path)
        sig = self.endpoint_parser.parse(self._ws_ep.unwrapped_func)
        if sig.body_param is not None:
            raise NotSupportedError(
                f"Websocket does not support body param, got {sig.body_param}"
            )
        self._ws_ep.setup(sig, self._graph)
        self.call_stack = self.chainup_middlewares(self._ws_ep)
        self._is_setup = True

    def endpoint(self, func: Any = None, **iprops: Unpack[IEndpointProps]) -> Any:
        props = EndpointProps.from_unpack(**iprops)
        ws_ep = WebSocketEndpoint(self._path, func=func, props=props)
        self._ws_ep = ws_ep
        return func

    def include_subroutes(self, *subs: Self, parent_prefix: str | None = None) -> None:
        warnings.warn(
            "WebSocketRoute.include_subroutes is deprecated and will be removed in 0.3.0; "
            "use WebSocketRoute.merge instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.merge(*subs, parent_prefix=parent_prefix)

    def merge(self, *subs: Self, parent_prefix: str | None = None) -> None:
        """
        Merge other websocket routes into current route as sub routes,
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
            if sub._ws_ep is not None:
                new_sub.endpoint(sub._ws_ep.unwrapped_func, **sub._ws_ep.props)
            for sub_sub in sub_subs:
                new_sub.merge(sub_sub, parent_prefix=sub._path)
            self._subroutes.append(new_sub)
