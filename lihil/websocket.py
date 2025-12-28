import warnings
from concurrent.futures import ThreadPoolExecutor
from inspect import iscoroutinefunction
from typing import Any, TypedDict

from ididi import Graph, Resolver
from typing_extensions import Self, Unpack

from lihil.channel import (
    TOPIC_NOT_FOUND,
    Channel,
    ISocket,
    MessageEnvelope,
    RejectError,
)
from lihil.errors import NotSupportedError
from lihil.interface import (
    ASGIApp,
    Func,
    IAsyncFunc,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
)
from lihil.routing import EndpointInfo, EndpointProps, IEndpointProps, RouteBase
from lihil.signature import EndpointParser, EndpointSignature, Injector, ParseResult
from lihil.utils.string import merge_path
from lihil.vendors import Response, WebSocket, WebSocketDisconnect, WebSocketState


class PendingManaged(TypedDict, total=False):
    on_connect: IAsyncFunc[..., None]
    on_disconnect: IAsyncFunc[..., None]
    channels: list[Channel]


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
        self._injector = Injector(self._sig)
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
        ws = WebSocket(scope, receive, send)

        try:
            parsed = await self._injector.validate_websocket(ws, resolver)
            await self._func(**parsed.params)
        except WebSocketDisconnect:
            # we should not send close message when client is disconnected already
            return
        except Exception:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code=1011, reason="Internal Server Error")
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


class WSManagedEndpoint(WebSocketEndpoint):
    """Managed websocket endpoint with channel dispatch."""

    def __init__(
        self,
        path: str,
        func: Func[..., None],
        props: EndpointProps,
        *,
        on_connect: IAsyncFunc[..., None] | None = None,
        on_disconnect: IAsyncFunc[..., None] | None = None,
        channels: list[Channel] | None = None,
    ):
        super().__init__(path=path, func=func, props=props)
        self._channels: list[Channel] = list(channels) if channels else []
        self._on_connect: IAsyncFunc[..., None] | None = on_connect
        self._on_disconnect: IAsyncFunc[..., None] | None = on_disconnect

    @property
    def on_connect(self) -> IAsyncFunc[..., None] | None:
        return self._on_connect

    @on_connect.setter
    def on_connect(self, func: IAsyncFunc[..., None] | None) -> None:
        self._on_connect = func

    @property
    def on_disconnect(self) -> IAsyncFunc[..., None] | None:
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, func: IAsyncFunc[..., None] | None) -> None:
        self._on_disconnect = func

    @property
    def channels(self):
        return self._channels

    def add_channel(self, channel: Channel) -> Channel:
        self._channels.append(channel)
        self._channels.sort(key=lambda c: c.topic_pattern.count("{"), reverse=True)
        return channel

    def match_channel(self, topic: str) -> tuple[Channel | None, dict[str, str] | None]:
        for ch in self._channels:
            if params := ch.match(topic):
                return ch, params
        return None, None

    async def make_call(
        self,
        scope: IScope,
        receive: IReceive,
        send: ISend,
        resolver: Resolver,
    ) -> None | ParseResult | Response:
        ws = WebSocket(scope, receive, send)
        sock = ISocket(ws)
        joined: set[Channel] = set()

        parsed_params: dict[str, Any] | None = None

        try:
            parsed = await self._injector.validate_websocket(ws, resolver)
            parsed_params = dict(parsed.params)
            if self._on_connect:
                await self._on_connect(sock, **parsed_params)
            await ws.accept()

            while True:
                env_raw = await ws.receive_json()
                env = MessageEnvelope.from_raw(env_raw)
                ch, match = self.match_channel(env.topic)
                sock.topic = env.topic
                sock.params = match or {}
                env.topic_params = match or {}

                if not ch:
                    await ws.send_json(TOPIC_NOT_FOUND)
                    return

                await ch.dispatch(env, sock, joined)

        except WebSocketDisconnect:
            pass
        except RejectError:
            return
        except Exception:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code=1011, reason="Internal Server Error")
            raise
        finally:
            for ch in joined:
                if ch.exit_handler:
                    await ch.exit_handler(sock)
            if self._on_disconnect and parsed_params is not None:
                await self._on_disconnect(sock, **parsed_params)
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close()


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
        self._pending: PendingManaged = {}

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

    def handler(
        self, func: Func[..., None], **iprops: Unpack[IEndpointProps]
    ) -> Func[..., None]:
        props = EndpointProps.from_unpack(**iprops)
        if self._ws_ep is not None:
            raise RuntimeError("Managed handler cannot be mixed with existing endpoint")
        self._ws_ep = WSManagedEndpoint(
            self._path, func=func, props=props, **self._pending
        )
        self._pending = {}
        return func

    def on_connect(self, func: IAsyncFunc[..., None]) -> IAsyncFunc[..., None]:
        if self._ws_ep is None:
            self._pending["on_connect"] = func
            return func
        if not isinstance(self._ws_ep, WSManagedEndpoint):
            raise RuntimeError(
                "Managed on_connect cannot be mixed with low-level endpoint"
            )
        self._ws_ep.on_connect = func
        return func

    def on_disconnect(self, func: IAsyncFunc[..., None]) -> IAsyncFunc[..., None]:
        if self._ws_ep is None:
            self._pending["on_disconnect"] = func
            return func
        if not isinstance(self._ws_ep, WSManagedEndpoint):
            raise RuntimeError(
                "Managed on_disconnect cannot be mixed with low-level endpoint"
            )
        self._ws_ep.on_disconnect = func
        return func

    def channel(self, pattern: str) -> Channel:
        ch = Channel(pattern)
        if self._ws_ep is None:
            channels = self._pending.setdefault("channels", [])
            channels.append(ch)
        elif isinstance(self._ws_ep, WSManagedEndpoint):
            self._ws_ep.add_channel(ch)
        else:
            raise RuntimeError(
                "Managed channel cannot be mixed with low-level endpoint"
            )
        return ch

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
                if isinstance(sub._ws_ep, WSManagedEndpoint):
                    new_sub._ws_ep = WSManagedEndpoint(
                        new_sub._path,
                        func=sub._ws_ep.unwrapped_func,
                        props=sub._ws_ep.props,
                        on_connect=sub._ws_ep.on_connect,
                        on_disconnect=sub._ws_ep.on_disconnect,
                        channels=list(sub._ws_ep.channels),
                    )
                else:
                    new_sub.endpoint(sub._ws_ep.unwrapped_func, **sub._ws_ep.props)
            for sub_sub in sub_subs:
                new_sub.merge(sub_sub, parent_prefix=sub._path)
            self._subroutes.append(new_sub)
