import warnings
from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial
from types import MappingProxyType
from typing import Any, Callable, cast, overload

from ididi import Graph
from typing_extensions import Self, Unpack

from lihil.asgi import ASGIRoute
from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.errors import InvalidEndpointError, LihilError
from lihil.interface import (
    HTTP_METHODS,
    ASGIApp,
    Func,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    P,
    R,
)

# from lihil.oas.model import OASResponse
from lihil.signature import EndpointParser
from lihil.utils.string import generate_route_tag, merge_path

from .endpoint import Endpoint, EndpointProps, IEndpointProps


class Route(ASGIRoute):
    def __init__(
        self,
        path: str = "",
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        workers: ThreadPoolExecutor | None = None,
        **iprops: Unpack[IEndpointProps],
    ):
        super().__init__(path, graph=graph, middlewares=middlewares, workers=workers)
        self._endpoints: dict[HTTP_METHODS, Endpoint[Any]] = {}
        self._call_stacks: dict[HTTP_METHODS, ASGIApp] = {}

        if iprops:
            self._props = EndpointProps.from_unpack(**iprops)
        else:
            self._props = EndpointProps()

        if self._props.deps:
            for dep in self._props.deps:
                self._graph.node(dep)

        self._is_setup: bool = False

    @property
    def endpoints(self) -> MappingProxyType[HTTP_METHODS, Endpoint[Any]]:
        return MappingProxyType(self._endpoints)

    @property
    def props(self) -> EndpointProps:
        return self._props

    def __repr__(self) -> str:
        endpoints_repr = "".join(
            f", {method}: {endpoint.unwrapped_func}"
            for method, endpoint in self._endpoints.items()
        )
        return f"{self.__class__.__name__}({self._path!r}{endpoints_repr})"

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        endpoint = self._call_stacks.get(scope["method"], METHOD_NOT_ALLOWED_RESP)
        await endpoint(scope, receive, send)

    def setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ) -> None:
        super().setup(workers=workers, graph=graph)
        self.endpoint_parser = EndpointParser(self._graph, self._path)

        for method, ep in self._endpoints.items():
            if ep.is_setup:
                continue
            try:
                ep_sig = self.endpoint_parser.parse(ep.unwrapped_func)
                ep.setup(ep_sig, self._graph)
            except LihilError as le:
                raise InvalidEndpointError(f"Failed to setup {ep}") from le
            self._call_stacks[method] = self.chainup_middlewares(ep)
        self._is_setup = True

    def include_subroutes(self, *subs: Self, parent_prefix: str | None = None) -> None:
        warnings.warn(
            "Route.include_subroutes is deprecated and will be removed in 0.3.0; "
            "use Route.merge instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.merge(*subs, parent_prefix=parent_prefix)

    def merge(self, *subs: Self, parent_prefix: str | None = None) -> None:
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
                **sub._props,
            )
            for method, ep in sub._endpoints.items():
                new_sub.add_endpoint(method, func=ep.unwrapped_func, **ep.props)
            for sub_sub in sub_subs:
                new_sub.merge(sub_sub, parent_prefix=sub._path)
            self._subroutes.append(new_sub)

    def get_endpoint(
        self, method_func: HTTP_METHODS | Callable[..., Any]
    ) -> Endpoint[Any]:
        if not self._is_setup:
            self.setup()

        if isinstance(method_func, str):
            methodname = cast(HTTP_METHODS, method_func.upper())
            return self._endpoints[methodname]

        for ep in self._endpoints.values():
            if ep.unwrapped_func is method_func:
                return ep
        else:
            raise KeyError(f"{method_func} is not in current route")

    def add_endpoint(
        self,
        *methods: HTTP_METHODS,
        func: Func[P, R],
        **endpoint_props: Unpack[IEndpointProps],
    ) -> Func[P, R]:

        if endpoint_props:
            new_props = EndpointProps.from_unpack(**endpoint_props)
            props = self._props.merge(new_props, deduplicate=True)
        else:
            props = self._props

        if not props.tags:
            props = props.replace(tags=[generate_route_tag(self._path)])

        for method in methods:
            endpoint = Endpoint(
                self._path, method=method, func=func, props=props, workers=self._workers
            )
            self._endpoints[method] = endpoint

        return func

    # ============ Http Methods ================

    @overload
    def get(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def get(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def get(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]: ...

    def get(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        if func is None:
            return cast(Func[P, R], partial(self.get, **epconfig))
        return self.add_endpoint("GET", func=func, **epconfig)

    @overload
    def put(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def put(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def put(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def put(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.put, **epconfig))
        return self.add_endpoint("PUT", func=func, **epconfig)

    @overload
    def post(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def post(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def post(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def post(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.post, **epconfig))
        return self.add_endpoint("POST", func=func, **epconfig)

    @overload
    def delete(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def delete(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def delete(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def delete(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.delete, **epconfig))
        return self.add_endpoint("DELETE", func=func, **epconfig)

    @overload
    def patch(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def patch(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def patch(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def patch(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.patch, **epconfig))
        return self.add_endpoint("PATCH", func=func, **epconfig)

    @overload
    def head(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def head(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def head(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def head(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.head, **epconfig))
        return self.add_endpoint("HEAD", func=func, **epconfig)

    @overload
    def options(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def options(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def options(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def options(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("OPTIONS", func=func, **epconfig)

    @overload
    def trace(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def trace(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def trace(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def trace(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("TRACE", func=func, **epconfig)

    @overload
    def connect(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def connect(self, func: Func[P, R]) -> Func[P, R]: ...

    @overload
    def connect(
        self, func: Func[P, R] | None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]: ...

    def connect(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        if func is None:
            return cast(Func[P, R], partial(self.options, **epconfig))
        return self.add_endpoint("CONNECT", func=func, **epconfig)
