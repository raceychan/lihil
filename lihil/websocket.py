from inspect import iscoroutinefunction
from typing import Any, Mapping, cast

from ididi import Graph, Resolver
from starlette.responses import Response

from lihil.errors import NotSupportedError
from lihil.interface import ASGIApp, Func, IReceive, IScope, ISend
from lihil.plugins.bus import BusTerminal, EventBus
from lihil.problems import InvalidRequestErrors
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
        self._app_state = self._route.app_state
        self._sig = self._route.endpoint_parser.parse(self._unwrapped_func)

        self._dep_items = self._sig.dependencies.items()
        self._states_items = self._sig.states.items()

        if self._sig.body_param is not None:
            raise NotSupportedError("websocket does not support body param")

        self._scoped: bool = self._sig.scoped

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._route.path!r} {self._func})"

    def inject_states(
        self, params: dict[str, Any], websocket: WebSocket, resolver: Resolver
    ):
        for name, p in self._states_items:
            ptype = cast(type, p.type_)
            if issubclass(ptype, WebSocket):
                params[name] = websocket
            elif issubclass(ptype, EventBus):
                bus = self._busterm.create_event_bus(resolver)
                params[name] = bus
            elif issubclass(ptype, Resolver):
                params[name] = resolver
            else:  # AppState
                if (state := self._app_state) is None:
                    raise ValueError(
                        f"{self} requires state param {name}, but app state is not set"
                    )
                params[name] = state[name]

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
            self.inject_states(params, ws, resolver)

            for name, dep in self._dep_items:
                params[name] = await resolver.aresolve(dep.dependent, **params)

            await self._func(**params)
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

    def setup(
        self,
        graph: Graph | None = None,
        busterm: BusTerminal | None = None,
        app_state: Mapping[str, Any] | None = None,
    ):
        super().setup(graph=graph, busterm=busterm, app_state=app_state)
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
