from functools import partial
from types import MethodType
from typing import Any, Callable, Pattern, Union, Unpack, cast, overload

from ididi import Graph, INodeConfig
from ididi.interfaces import IDependent

from lihil.asgi import ASGIBase
from lihil.config import EndPointConfig, IEndPointConfig
from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.endpoint import Endpoint
from lihil.interface import (
    HTTP_METHODS,
    ASGIApp,
    Func,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    Protocol,
)
from lihil.oas.model import RouteConfig
from lihil.plugins.bus import BusTerminal, Event, MessageRegistry
from lihil.utils.parse import (
    build_path_regex,
    generate_route_tag,
    merge_path,
    trim_path,
)


class EndpointFactory[R](Protocol):
    def __call__(
        self,
        method: HTTP_METHODS,
        path: str,
        tag: str,
        func: Callable[..., R],
        busterm: BusTerminal,
        graph: Graph,
        epconfig: EndPointConfig,
    ) -> Endpoint[R]: ...


def endpoint_factory[R](
    method: HTTP_METHODS,
    path: str,
    tag: str,
    func: Callable[..., R],
    busterm: BusTerminal,
    graph: Graph,
    epconfig: EndPointConfig,
) -> Endpoint[R]:
    endpoint = Endpoint(
        method=method,
        path=path,
        tag=tag,
        func=func,
        busterm=busterm,
        graph=graph,
        config=epconfig,
    )
    return endpoint


class Route(ASGIBase):
    _flyweights: dict[str, "Route"] = {}

    def __new__(cls, path: str = "", **_):
        """
        TODO?: we need something more sophisticated

        Route("/users/{user_id}/orders/{order_id}")
        we should know check if `Route(/users/{user_id}/orders)` is in _flyweight,
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
        route_config: RouteConfig | None = None,
        endpoint_factory: EndpointFactory[Any] = endpoint_factory,
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
        self.config = route_config or RouteConfig()
        self.endpoint_factory = endpoint_factory
        self.tag = self.config.tag or generate_route_tag(self.path)

    def __repr__(self):
        endpoints_repr = "".join(
            f", {method}: {endpoint.unwrapped_func}"
            for method, endpoint in self.endpoints.items()
        )
        return f"{self.__class__.__name__}({self.path!r}{endpoints_repr})"

    def __truediv__(self, path: str) -> "Route":
        return self.sub(path)

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend):
        http_method = scope["method"]
        try:
            await self.call_stacks[http_method](scope, receive, send)
        except KeyError:
            return await METHOD_NOT_ALLOWED_RESP(scope, receive, send)

    def is_direct_child_of(self, other: "Route") -> bool:
        if not self.path.startswith(other.path):
            return False
        rest = self.path.removeprefix(other.path)
        return rest.count("/") < 2

    def setup(self):
        for method, ep in self.endpoints.items():
            ep.setup()
            self.call_stacks[method] = self.chainup_middlewares(ep)

    def sync_deps(self, graph: Graph, busterm: BusTerminal):
        self.graph = graph
        self.busterm = busterm

        for ep in self.endpoints.values():
            ep.sync_deps(graph, busterm)

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
        **iconfig: Unpack[IEndPointConfig],
    ) -> Func[P, R]:
        epconfig = EndPointConfig.from_unpack(**iconfig)
        # TODO: use a end point factory that user can override
        for method in methods:
            endpoint = self.endpoint_factory(
                method=method,
                path=self.path,
                tag=self.tag,
                func=func,
                busterm=self.busterm,
                graph=self.graph,
                epconfig=epconfig,
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
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def get[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def get[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]: ...

    def get[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        if func is None:
            return cast(Func[P, R], partial(self.get, **epconfig))
        return self.add_endpoint("GET", func=func, **epconfig)

    @overload
    def put[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def put[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def put[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def put[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.put, **epconfig))
        return self.add_endpoint("PUT", func=func, **epconfig)

    @overload
    def post[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def post[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def post[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def post[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.post, **epconfig))
        return self.add_endpoint("POST", func=func, **epconfig)

    @overload
    def delete[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def delete[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def delete[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def delete[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.delete, **epconfig))
        return self.add_endpoint("DELETE", func=func, **epconfig)

    @overload
    def patch[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def patch[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def patch[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def patch[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.patch, **epconfig))
        return self.add_endpoint("PATCH", func=func, **epconfig)

    @overload
    def head[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def head[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def head[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def head[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.head, **epconfig))
        return self.add_endpoint("HEAD", func=func, **epconfig)

    @overload
    def options[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def options[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def options[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def options[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("OPTIONS", func=func, **epconfig)

    @overload
    def trace[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def trace[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def trace[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def trace[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("TRACE", func=func, **epconfig)

    @overload
    def connect[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def connect[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def connect[**P, R](
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]: ...

    def connect[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("CONNECT", func=func, **epconfig)
