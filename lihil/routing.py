from functools import partial
from types import MethodType
from typing import Any, Callable, Pattern, Sequence, Union, Unpack, cast

from ididi import Graph, INodeConfig
from ididi.interfaces import IDependent

from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.endpoint import Endpoint, EndPointConfig, IEndPointConfig
from lihil.interface import HTTP_METHODS, Func, IReceive, IScope, ISend
from lihil.interface.asgi import ASGIApp, MiddlewareFactory
from lihil.oas.model import IOASConfig, OASConfig
from lihil.utils.parse import (
    build_path_regex,
    generate_route_tag,
    handle_path,
    merge_path,
)


class Route:
    _flyweights: dict[str, "Route"] = {}

    def __new__(cls, path: str = "", **_):
        p = handle_path(path)
        if p_route := cls._flyweights.get(p):
            return p_route
        cls._flyweights[p] = route = super().__new__(cls)
        return route

    def __init__(  # type: ignore
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        tag: str = "",
        **oas_config: Unpack[IOASConfig],
    ):
        self.path = handle_path(path)
        self.path_regex: Pattern[str] | None = None
        self.endpoints: dict[HTTP_METHODS, Endpoint[Any]] = {}
        self.graph = graph or Graph()
        self.tag = tag or generate_route_tag(self.path)
        self.subroutes: list[Route] = []
        self.middle_factories: list[MiddlewareFactory[Any]] = []
        self.call_stacks: dict[HTTP_METHODS, ASGIApp] = {}
        self.oas_config = OASConfig(**oas_config)

    def __repr__(self):
        endpoints_repr = "".join(
            f", {method}: {endpoint.func}"
            for method, endpoint in self.endpoints.items()
        )
        return f"{self.__class__.__name__}({self.path!r}{endpoints_repr})"

    def __truediv__(self, path: str) -> "Route":
        return self.sub(path)

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend):
        http_method = scope["method"]
        # TODO: chainup middlewares at lifespan
        try:
            cs = self.call_stacks[http_method]
        except KeyError:
            try:
                ep = self.endpoints[http_method]
            except KeyError:
                return await METHOD_NOT_ALLOWED_RESP(scope, receive, send)
            self.call_stacks[http_method] = cs = self.chainup_middlewares(ep)
        await cs(scope, receive, send)

    def is_direct_child_of(self, other: "Route") -> bool:
        if not self.path.startswith(other.path):
            return False
        rest = self.path.removeprefix(other.path)
        return rest.count("/") < 2

    def build_stack(self):
        for method, ep in self.endpoints.items():
            self.call_stacks[method] = self.chainup_middlewares(ep)

    def chainup_middlewares(self, tail: ASGIApp) -> ASGIApp:
        # TODO: use graph to inject middleware factories
        current = tail
        for factory in reversed(self.middle_factories):
            prev = factory(current)
            current = prev
        return current

    def get_endpoint(
        self, method_func: HTTP_METHODS | Callable[..., Any]
    ) -> Endpoint[Any]:
        if isinstance(method_func, str):
            return self.endpoints[method_func]
        for ep in self.endpoints.values():
            if ep.func is method_func:
                return ep
        else:
            raise KeyError(f"{method_func} is not in current route")

    def sub(self, path: str) -> "Route":
        sub_path = handle_path(path)
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
        self, method: HTTP_METHODS, func: Func[P, R], **iconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        epconfig = EndPointConfig.from_unpack(**iconfig)
        endpoint = Endpoint(
            method=method,
            path=self.path,
            tag=self.tag,
            func=func,
            graph=self.graph,
            config=epconfig,
        )
        self.endpoints[method] = endpoint
        if self.path_regex is not None:
            return func
        self.path_regex = build_path_regex(self.path)
        return func

    def add_middleware[T: ASGIApp](
        self,
        middleware_factories: MiddlewareFactory[T] | Sequence[MiddlewareFactory[T]],
    ) -> None:
        """
        Accept one or a sequence of factories for ASGI middlewares
        """

        if isinstance(middleware_factories, Sequence):
            self.middle_factories = list(middleware_factories) + self.middle_factories
        else:
            self.middle_factories.insert(0, middleware_factories)

    def get[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        if func is None:
            return cast(Func[P, R], partial(self.get, **epconfig))
        return self.add_endpoint("GET", func, **epconfig)

    def put[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.put, **epconfig))
        return self.add_endpoint("PUT", func, **epconfig)

    def post[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.post, **epconfig))
        return self.add_endpoint("POST", func, **epconfig)

    def delete[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.delete, **epconfig))
        return self.add_endpoint("DELETE", func, **epconfig)


