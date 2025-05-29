from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial
from inspect import isasyncgen, iscoroutinefunction, isgenerator
from types import MethodType
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    Literal,
    Pattern,
    Sequence,
    TypedDict,
    Union,
    cast,
    overload,
)

from ididi import Graph, INodeConfig
from ididi.graph import Resolver
from ididi.interfaces import IDependent
from msgspec import field
from starlette.responses import StreamingResponse
from typing_extensions import Self, Unpack

from lihil.asgi import ASGIBase
from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.ds.resp import StaticResponse
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
    Record,
    T,
)
from lihil.plugins import IPlugin
from lihil.plugins.auth.oauth import AuthBase
from lihil.problems import DetailBase, get_solver
from lihil.signature import EndpointParser, EndpointSignature, Injector, ParseResult
from lihil.signature.returns import agen_encode_wrapper, syncgen_encode_wrapper
from lihil.utils.string import (
    build_path_regex,
    generate_route_tag,
    merge_path,
    trim_path,
)
from lihil.utils.threading import async_wrapper
from lihil.vendors import Request, Response


class IEndpointProps(TypedDict, total=False):
    errors: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
    "Errors that might be raised from the current `endpoint`. These will be treated as responses and displayed in OpenAPI documentation."
    in_schema: bool
    "Whether to include this endpoint inside openapi docs"
    to_thread: bool
    "Whether this endpoint should be run wihtin a separate thread, only apply to sync function"
    scoped: Literal[True] | None
    "Whether current endpoint should be scoped"
    auth_scheme: AuthBase | None
    "Auth Scheme for access control"
    tags: Sequence[str] | None
    "OAS tag, endpoints with the same tag will be grouped together"
    plugins: list[IPlugin]
    "Decorators to decorate the endpoint function"


class EndpointProps(Record, kw_only=True):
    errors: tuple[type[DetailBase[Any]], ...] = field(default_factory=tuple)
    to_thread: bool = True
    in_schema: bool = True
    scoped: Literal[True] | None = None
    auth_scheme: AuthBase | None = None
    tags: Sequence[str] | None = None
    plugins: list[IPlugin] = field(default_factory=list[IPlugin])

    @classmethod
    def from_unpack(cls, **iconfig: Unpack[IEndpointProps]):
        if raw_errors := iconfig.get("errors"):
            if not isinstance(raw_errors, Sequence):
                errors = (raw_errors,)
            else:
                errors = tuple(raw_errors)

            iconfig["errors"] = errors
        return cls(**iconfig)  # type: ignore


class Endpoint(Generic[R]):
    def __init__(
        self,
        route: "Route",
        method: HTTP_METHODS,
        func: Callable[..., R],
        props: EndpointProps,
        workers: ThreadPoolExecutor | None,
    ):
        self._route = route
        self._method: HTTP_METHODS = method
        self._unwrapped_func = func
        self._func = async_wrapper(func, threaded=props.to_thread, workers=workers)
        self._props = props
        self._name = func.__name__
        self.__is_setup: bool = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._method}: {self._route.path!r} {self._func})"

    @property
    def route(self):
        return self._route

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

    @property
    def is_setup(self) -> bool:
        return self.__is_setup

    async def chainup_plugins(
        self, func: Callable[..., Awaitable[R]], sig: EndpointSignature[R]
    ) -> Callable[..., Awaitable[R]]:
        seen: set[int] = set()
        for decor in self._props.plugins:
            if (decor_id := id(decor)) in seen:
                continue
            if iscoroutinefunction(decor):
                wrapped = await decor(self._route.graph, func, sig)
            else:
                wrapped = decor(self._route.graph, func, sig)
            func = cast(Callable[..., Awaitable[R]], wrapped)
            seen.add(decor_id)
        return func

    async def setup(self, sig: EndpointSignature[R]) -> None:
        if self.__is_setup:
            raise Exception(f"`setup` is called more than once in {self}")

        self._graph = self._route.graph
        self._sig = sig
        self._func = await self.chainup_plugins(self._func, self._sig)
        self._injector = Injector(self._sig)

        self._static = sig.static
        self._status_code = sig.status_code
        self._scoped: bool = sig.scoped or self._props.scoped is True
        self._encoder = sig.encoder

        self._media_type = sig.media_type

        self.__is_setup = True

    async def make_static_call(
        self, scope: IScope, receive: IReceive, send: ISend
    ) -> R | Response:
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
            parsed = await self._injector.validate_request(request, resolver)
            params, callbacks = parsed.params, parsed.callbacks
            return await self._func(**params)
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
            return raw_return
        else:
            if isasyncgen(raw_return):
                encode_wrapper = agen_encode_wrapper(raw_return, self._encoder)
                resp = StreamingResponse(
                    encode_wrapper,
                    media_type="text/event-stream",
                    status_code=self._status_code,
                )
            elif isgenerator(raw_return):
                encode_wrapper = syncgen_encode_wrapper(raw_return, self._encoder)
                resp = StreamingResponse(
                    encode_wrapper,
                    media_type="text/event-stream",
                    status_code=self._status_code,
                )
            elif self._static:
                resp = StaticResponse(
                    self._encoder(raw_return),
                    media_type=self._media_type,
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


class RouteBase(ASGIBase):
    def __init__(  # type: ignore
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
    ):
        super().__init__(middlewares)
        self.path = trim_path(path)
        self.path_regex: Pattern[str] = build_path_regex(self.path)
        self.graph = graph or Graph(self_inject=False)
        self.workers = None
        self.subroutes: list[Self] = []

    def __truediv__(self, path: str) -> "Self":
        return self.sub(path)

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend): ...

    def is_direct_child_of(self, other_path: "Route | str") -> bool:
        if isinstance(other_path, Route):
            return self.is_direct_child_of(other_path.path)

        if not self.path.startswith(other_path):
            return False
        rest = self.path.removeprefix(other_path)
        return rest.count("/") < 2

    def sub(self, path: str) -> Self:
        sub_path = trim_path(path)
        merged_path = merge_path(self.path, sub_path)
        for sub in self.subroutes:
            if sub.path == merged_path:
                return sub
        sub = self.__class__(
            path=merged_path,
            graph=self.graph,
            middlewares=self.middle_factories,
        )
        self.subroutes.append(sub)
        return sub

    def match(self, scope: IScope) -> bool:
        path = scope["path"]
        if not self.path_regex or not (m := self.path_regex.match(path)):
            return False
        scope["path_params"] = m.groupdict()
        return True

    def add_nodes(
        self, *nodes: Union[IDependent[T], tuple[IDependent[T], INodeConfig]]
    ) -> None:
        self.graph.add_nodes(*nodes)

    def factory(self, node: Callable[..., R], **node_config: Unpack[INodeConfig]):
        return self.graph.node(node, **node_config)

    async def setup(
        self,
        graph: Graph | None = None,
        workers: ThreadPoolExecutor | None = None,
    ):
        self.graph = graph or self.graph
        self.workers = workers


class Route(RouteBase):

    def __init__(  # type: ignore
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        props: EndpointProps | None = None,
    ):
        super().__init__(
            path,
            graph=graph,
            middlewares=middlewares,
        )
        self.endpoints: dict[HTTP_METHODS, Endpoint[Any]] = {}
        self.call_stacks: dict[HTTP_METHODS, ASGIApp] = {}
        if props is not None:
            if props.tags is None:
                props = props.replace(tags=generate_route_tag(self.path))
            self.props = props
        else:
            self.props = EndpointProps(tags=[generate_route_tag(self.path)])

    def __repr__(self):
        endpoints_repr = "".join(
            f", {method}: {endpoint.unwrapped_func}"
            for method, endpoint in self.endpoints.items()
        )
        return f"{self.__class__.__name__}({self.path!r}{endpoints_repr})"

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        endpoint = self.call_stacks.get(scope["method"]) or METHOD_NOT_ALLOWED_RESP
        await endpoint(scope, receive, send)

    async def setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ):
        await super().setup(workers=workers, graph=graph)
        self.endpoint_parser = EndpointParser(self.graph, self.path)

        for method, ep in self.endpoints.items():
            if ep.is_setup:
                continue
            ep_sig = self.endpoint_parser.parse(ep.unwrapped_func)
            await ep.setup(ep_sig)
            self.call_stacks[method] = self.chainup_middlewares(ep)

    def parse_endpoint(self, func: Callable[..., R]) -> EndpointSignature[R]:
        return self.endpoint_parser.parse(func)

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

    def include_subroutes(self, *subs: Self, parent_prefix: str | None = None) -> None:
        """
        Merge other routes into current route as sub routes,
        a new route would be created based on the merged subroute

        NOTE: This method is NOT idempotent
        """
        for sub in subs:
            self.graph.merge(sub.graph)
            if parent_prefix:
                sub_path = sub.path.removeprefix(parent_prefix)
            else:
                sub_path = sub.path
            merged_path = merge_path(self.path, sub_path)
            sub_subs = sub.subroutes
            new_sub = self.__class__(
                path=merged_path,
                graph=self.graph,
                middlewares=sub.middle_factories,
                props=sub.props,
            )
            for method, ep in sub.endpoints.items():
                new_sub.add_endpoint(method, func=ep.unwrapped_func, **ep.props)
            for sub_sub in sub_subs:
                new_sub.include_subroutes(sub_sub, parent_prefix=sub.path)
            self.subroutes.append(new_sub)

    def redirect(self, method: MethodType, **path_params: str) -> None:
        # owner = method.__self__
        raise NotImplementedError

    def add_endpoint(
        self,
        *methods: HTTP_METHODS,
        func: Func[P, R],
        **endpoint_props: Unpack[IEndpointProps],
    ) -> Func[P, R]:

        if endpoint_props:
            new_props = EndpointProps.from_unpack(**endpoint_props)
            props = self.props.merge(new_props)
        else:
            props = self.props

        for method in methods:
            endpoint = Endpoint(
                self, method=method, func=func, props=props, workers=self.workers
            )
            self.endpoints[method] = endpoint

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
