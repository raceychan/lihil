from functools import partial
from inspect import isasyncgen, isgenerator
from types import MethodType
from typing import Any, Callable, Pattern, Union, Unpack, cast, overload

from ididi import Graph, INodeConfig
from ididi.graph import Resolver
from ididi.interfaces import IDependent
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from lihil.asgi import ASGIBase
from lihil.config import AppConfig, SyncDeps
from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.endpoint import EndpointSignature, ParseResult
from lihil.endpoint.endpoint import EndpointProps, IEndpointProps
from lihil.endpoint.returns import agen_encode_wrapper, syncgen_encode_wrapper
from lihil.errors import InvalidParamTypeError
from lihil.interface import (
    HTTP_METHODS,
    ASGIApp,
    Func,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
)
from lihil.plugins.bus import BusTerminal, Event, EventBus, MessageRegistry
from lihil.problems import InvalidRequestErrors, get_solver
from lihil.props import EndpointProps
from lihil.props import IEndpointProps as IEndpointProps
from lihil.utils.string import (
    build_path_regex,
    generate_route_tag,
    merge_path,
    trim_path,
)
from lihil.utils.threading import async_wrapper


class Endpoint[R]:
    def __init__(
        self,
        route: "Route",
        method: HTTP_METHODS,
        func: Callable[..., R],
        props: EndpointProps,
    ):
        self._route = route
        self._graph = route.graph
        self._busterm = route.busterm
        self._method: HTTP_METHODS = method
        self._unwrapped_func = func
        self._func = async_wrapper(func, threaded=props.to_thread)
        self._props = props
        self._name = func.__name__

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._method}: {self._route.path!r} {self._func})"

    @property
    def props(self):
        return self._props

    @property
    def path(self) -> str:
        return self._route.path

    @property
    def name(self) -> str:
        return self._name

    @property
    def sig(self) -> EndpointSignature[R]:
        return self._sig

    @property
    def method(self) -> HTTP_METHODS:
        return self._method

    @property
    def scoped(self) -> bool:
        return self._scoped

    @property
    def encoder(self):
        return self._encoder

    @property
    def unwrapped_func(self) -> Callable[..., R]:
        return self._unwrapped_func

    def setup(self) -> None:
        self._sig = EndpointSignature.from_function(
            graph=self._route.graph,
            route_path=self._route.path,
            f=self._unwrapped_func,
            app_config=self._route.app_config,
        )

        self._dep_items = self._sig.dependencies.items()
        self._plugin_items = self._sig.plugins.items()

        self._static = not any(
            (
                self._sig.path_params,
                self._sig.query_params,
                self._sig.header_params,
                self._sig.body_param,
                self._sig.dependencies,
                self._sig.plugins,
            )
        )

        scoped_by_config = bool(self._props and self._props.scoped is True)

        self._require_body: bool = self._sig.body_param is not None
        self._status_code = self._sig.default_status
        self._scoped: bool = self._sig.scoped or scoped_by_config
        self._encoder = self._sig.return_encoder
        self._media_type = next(iter(self._sig.return_params.values())).content_type

    async def inject_plugins(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ):
        for name, p in self._plugin_items:
            ptype = p.type_
            assert isinstance(ptype, type)

            if issubclass(ptype, Request):
                params[name] = request
            elif issubclass(ptype, EventBus):
                bus = self._busterm.create_event_bus(resolver)
                params[name] = bus
            elif issubclass(ptype, Resolver):
                params[name] = resolver
            elif p.processor:
                await p.processor(params, request, resolver)
            else:
                raise InvalidParamTypeError(ptype)
        return params

    async def make_static_call(self, scope: IScope, receive: IReceive, send: ISend):
        try:
            return await self._func()
        except Exception as exc:
            request = Request(scope, receive, send)
            if solver := get_solver(exc):
                return solver(request, exc)
            raise

    async def make_call(
        self, scope: IScope, receive: IReceive, send: ISend, resolver: Resolver
    ) -> R | ParseResult | Response:
        request = Request(scope, receive, send)
        callbacks = None
        try:
            if self._require_body:
                parsed_result = await self._sig.parse_command(request)
            else:
                parsed_result = self._sig.parse_query(request)

            callbacks = parsed_result.callbacks
            if errors := parsed_result.errors:
                raise InvalidRequestErrors(detail=errors)

            if self._plugin_items:
                params = await self.inject_plugins(
                    parsed_result.params, request, resolver
                )
            else:
                params = parsed_result.params

            for name, dep in self._dep_items:
                params[name] = await resolver.aresolve(dep.dependent, **params)

            raw_return = await self._func(**params)
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
                encode_wrapper = syncgen_encode_wrapper(raw_return, self._encoder)
            else:
                encode_wrapper = agen_encode_wrapper(raw_return, self._encoder)
            resp = StreamingResponse(
                encode_wrapper,
                media_type="text/event-stream",
                status_code=self._status_code,
            )
        else:
            resp = Response(
                content=self._encoder(raw_return),
                media_type=self._media_type,
                status_code=self._status_code,
            )
        return resp

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if self._scoped:
            async with self._graph.ascope() as resolver:
                raw_return = await self.make_call(scope, receive, send, resolver)
                response = self.return_to_response(raw_return)
            return await response(scope, receive, send)

        if self._static:  # when there is no params at all
            raw_return = await self.make_static_call(scope, receive, send)
        else:
            raw_return = await self.make_call(scope, receive, send, self._graph)

        response = self.return_to_response(raw_return)
        await response(scope, receive, send)


class Route(ASGIBase):
    _flyweights: dict[str, "Route"] = {}

    def __new__(cls, path: str = "", **_):
        """
        TODO?: we need something more sophisticated

        Route("/users/{user_id}/orders/{order_id}")
        we should check if `Route(/users/{user_id}/orders)` is in _flyweight,
        if parent exists, make new route a sub route of it.
        if not, pass
        """
        p = trim_path(path)
        if p_route := cls._flyweights.get(p):
            return p_route
        cls._flyweights[p] = route = super().__new__(cls)
        return route

    def __init__(  # type: ignore
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        registry: MessageRegistry | None = None,
        listeners: list[Callable[..., Any]] | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        # endpoint_factory: EndpointFactory[Any] = endpoint_factory,
        props: EndpointProps | None = None,
    ):
        super().__init__(middlewares)

        self.path = trim_path(path)
        self.path_regex: Pattern[str] | None = None
        self.endpoints: dict[HTTP_METHODS, Endpoint[Any]] = {}
        self.graph = graph or Graph(self_inject=False)
        self.registry = registry or MessageRegistry(event_base=Event, graph=graph)
        if listeners:
            self.registry.register(*listeners)
        self.busterm = BusTerminal(self.registry, graph=graph)
        self.subroutes: list[Route] = []
        self.call_stacks: dict[HTTP_METHODS, ASGIApp] = {}
        self.props = props or EndpointProps()
        self.app_config = None
        # self.endpoint_factory = endpoint_factory

        if self.props.tags:
            self.tags = self.props.tags
        else:
            aggregate_tag = generate_route_tag(self.path)
            self.tags = [aggregate_tag]

    def __repr__(self):
        endpoints_repr = "".join(
            f", {method}: {endpoint.unwrapped_func}"
            for method, endpoint in self.endpoints.items()
        )
        return f"{self.__class__.__name__}({self.path!r}{endpoints_repr})"

    def __truediv__(self, path: str) -> "Route":
        return self.sub(path)

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        endpoint = self.call_stacks.get(scope["method"]) or METHOD_NOT_ALLOWED_RESP
        await endpoint(scope, receive, send)

    def is_direct_child_of(self, other_path: "Route | str") -> bool:
        if isinstance(other_path, Route):
            return self.is_direct_child_of(other_path.path)

        if not self.path.startswith(other_path):
            return False
        rest = self.path.removeprefix(other_path)
        return rest.count("/") < 2

    def setup(self, **deps: Unpack[SyncDeps]):
        if deps:
            self.app_config = deps.get("app_config") or self.app_config
            self.graph = deps.get("graph") or self.graph
            self.busterm = deps.get("busterm") or self.busterm

        for method, ep in self.endpoints.items():
            ep.setup()
            self.call_stacks[method] = self.chainup_middlewares(ep)

    def get_endpoint(
        self, method_func: HTTP_METHODS | Callable[..., Any]
    ) -> Endpoint[Any]:
        if isinstance(method_func, str):
            methodname = cast(HTTP_METHODS, method_func.upper())
            return self.endpoints[methodname]

        for ep in self.endpoints.values():
            if ep.unwrapped_func is method_func:
                return ep
        else:
            raise KeyError(f"{method_func} is not in current route")

    def sub(self, path: str) -> "Route":
        sub_path = trim_path(path)
        current_path = merge_path(self.path, sub_path)
        sub = Route(path=current_path, graph=self.graph)
        self.subroutes.append(sub)
        return sub

    def match(self, scope: IScope) -> IScope | None:
        path = scope["path"]
        if not self.path_regex or not (m := self.path_regex.match(path)):
            return None
        scope["path_params"] = m.groupdict()
        return scope

    def add_nodes[T](
        self, *nodes: Union[IDependent[T], tuple[IDependent[T], INodeConfig]]
    ) -> None:
        self.graph.add_nodes(*nodes)

    def redirect(self, method: MethodType, **path_params: str) -> None:
        # owner = method.__self__
        raise NotImplementedError

    def add_endpoint[**P, R](
        self,
        *methods: HTTP_METHODS,
        func: Func[P, R],
        **iconfig: Unpack[IEndpointProps],
    ) -> Func[P, R]:
        if not iconfig.get("tags"):
            iconfig["tags"] = self.tags
        props = EndpointProps.from_unpack(**iconfig)
        # TODO: merge props

        # TODO: use a end point factory that user can override
        for method in methods:
            endpoint = Endpoint(
                self,
                method=method,
                func=func,
                props=props,
            )
            self.endpoints[method] = endpoint
            if self.path_regex is not None:
                return func
            self.path_regex = build_path_regex(self.path)
        return func

    def factory[R](self, node: Callable[..., R], **node_config: Unpack[INodeConfig]):
        return self.graph.node(node, **node_config)

    def listen(self, listener: Callable[[Event, Any], None]) -> None:
        self.registry.register(listener)

    def has_listener(self, listener: Callable[..., Any]) -> bool:
        event_metas = list(self.registry.event_mapping.values())

        for metas in event_metas:
            for meta in metas:
                if meta.handler is listener:
                    return True
        return False

    # ============ Http Methods ================

    @overload
    def get[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def get[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def get[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]: ...

    def get[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        if func is None:
            return cast(Func[P, R], partial(self.get, **epconfig))
        return self.add_endpoint("GET", func=func, **epconfig)

    @overload
    def put[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def put[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def put[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def put[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.put, **epconfig))
        return self.add_endpoint("PUT", func=func, **epconfig)

    @overload
    def post[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def post[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def post[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def post[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.post, **epconfig))
        return self.add_endpoint("POST", func=func, **epconfig)

    @overload
    def delete[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def delete[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def delete[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def delete[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.delete, **epconfig))
        return self.add_endpoint("DELETE", func=func, **epconfig)

    @overload
    def patch[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def patch[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def patch[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def patch[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.patch, **epconfig))
        return self.add_endpoint("PATCH", func=func, **epconfig)

    @overload
    def head[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def head[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def head[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def head[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.head, **epconfig))
        return self.add_endpoint("HEAD", func=func, **epconfig)

    @overload
    def options[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def options[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def options[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def options[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("OPTIONS", func=func, **epconfig)

    @overload
    def trace[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def trace[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def trace[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def trace[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("TRACE", func=func, **epconfig)

    @overload
    def connect[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def connect[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def connect[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def connect[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("CONNECT", func=func, **epconfig)
