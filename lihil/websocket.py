from functools import partial
from typing import Any, Unpack

from ididi import Graph, Resolver
from starlette.responses import Response

from lihil import EventBus
from lihil.errors import NotSupportedError
from lihil.interface import ASGIApp, Func, IReceive, IScope, ISend
from lihil.plugins.bus import BusTerminal
from lihil.problems import InvalidRequestErrors
from lihil.routing import (
    Endpoint,
    EndpointProps,
    IEndpointProps,
    Route,
    async_wrapper,
    build_path_regex,
)
from lihil.signature import ParseResult
from lihil.vendors import WebSocket


class WebSocketEndpoint(Endpoint[None]):
    def __init__(
        self, route: "WebSocketRoute", func: Func[..., None], props: EndpointProps
    ):
        self._route = route
        self._unwrapped_func = func
        self._func = async_wrapper(func, threaded=props.to_thread)
        self._props = props
        self._name = func.__name__

    def setup(self) -> None:
        super().setup()
        if self._require_body:
            raise NotSupportedError("websocket does not support body param")

    async def make_call(
        self,
        scope: IScope,
        receive: IReceive,
        send: ISend,
        resolver: Resolver,
    ) -> None | ParseResult | Response:
        ws = WebSocket(scope, receive, send)

        try:
            parsed_result = self._sig.parse_query(ws)
            if errors := parsed_result.errors:
                raise InvalidRequestErrors(detail=errors)

            params = parsed_result.params
            for name, p in self._plugin_items:
                ptype = p.type_
                assert isinstance(ptype, type)

                if issubclass(ptype, WebSocket):
                    params[name] = ws
                elif issubclass(ptype, EventBus):
                    bus = self._busterm.create_event_bus(resolver)
                    params[name] = bus
                elif issubclass(ptype, Resolver):
                    params[name] = resolver

                else:
                    params = parsed_result.params

                for name, dep in self._dep_items:
                    params[name] = await resolver.aresolve(dep.dependent, **params)

            await self._func(**params)
        except Exception as exc:
            await ws.close()
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


class WebSocketRoute(Route):
    endpoint: WebSocketEndpoint
    call_stack: ASGIApp | None = None

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if not self.call_stack:
            # raise Exception("not setup")
            self.call_stack = self.endpoint
        await self.call_stack(scope, receive, send)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.path!r})"

    def setup(self, graph: Graph | None = None, busterm: BusTerminal | None = None):
        super().setup(graph, busterm)
        self.endpoint.setup()
        self.call_stack = self.chainup_middlewares(self.endpoint)

    def socket(
        self,
        func: Any = None,
        **endpoint_props: Unpack[IEndpointProps],
    ) -> Any:
        if func is None:
            decor = partial(self.socket, **endpoint_props)
            return decor

        if endpoint_props:
            new_props = EndpointProps.from_unpack(**endpoint_props)
            props = self.props.merge(new_props)
        else:
            props = self.props

        endpoint = WebSocketEndpoint(
            self,
            func=func,
            props=props,
        )

        self.endpoint = endpoint
        if self.path_regex is None:
            self.path_regex = build_path_regex(self.path)
        return func
