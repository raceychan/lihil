from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial
from inspect import isasyncgen, isgenerator
from types import MappingProxyType
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
from lihil.errors import UnserializableResponseError
from lihil.interface import (
    HTTP_METHODS,
    ASGIApp,
    Func,
    IAsyncFunc,
    IEncoder,
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

DepNode = Union[IDependent[Any], tuple[IDependent[Any], INodeConfig]]


class IEndpointProps(TypedDict, total=False):
    problems: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
    "Errors that might be raised from the current `endpoint`. These will be treated as responses and displayed in OpenAPI documentation."
    in_schema: bool
    "Whether to include this endpoint inside openapi docs"
    to_thread: bool
    "Whether this endpoint should be run wihtin a separate thread, only apply to sync function"
    scoped: Literal[True] | None
    "Whether current endpoint should be scoped"
    auth_scheme: AuthBase | None
    "Auth Scheme for access control"
    tags: list[str] | None
    "OAS tag, endpoints with the same tag will be grouped together"
    encoder: IEncoder | None
    "Return Encoder"
    plugins: list[IPlugin]
    "Decorators to decorate the endpoint function"
    deps: list[DepNode] | None
    "Dependencies that might be used in "


class EndpointProps(Record, kw_only=True):
    problems: list[type[DetailBase[Any]]] = field(
        default_factory=list[type[DetailBase[Any]]]
    )
    to_thread: bool = True
    in_schema: bool = True
    scoped: Literal[True] | None = None
    auth_scheme: AuthBase | None = None
    tags: list[str] | None = None
    encoder: IEncoder | None = None
    plugins: list[IPlugin] = field(default_factory=list[IPlugin])
    deps: list[DepNode] | None = None

    @classmethod
    def from_unpack(cls, **iconfig: Unpack[IEndpointProps]):
        if problems := iconfig.get("problems"):
            if not isinstance(problems, Sequence):
                problems = [problems]

            iconfig["problems"] = problems
        return cls(**iconfig)  # type: ignore


class EndpointInfo(Record, Generic[P, R]):
    graph: Graph
    func: IAsyncFunc[P, R]
    sig: EndpointSignature[R]


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
        self._is_setup: bool = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._method}: {self._route.path!r} {self._func})"

    @property
    def route(self) -> "Route":
        return self._route

    @property
    def props(self) -> EndpointProps:
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
    def encoder(self) -> Callable[[Any], bytes]:
        return self._encoder

    @property
    def unwrapped_func(self) -> Callable[..., R]:
        return self._unwrapped_func

    @property
    def is_setup(self) -> bool:
        return self._is_setup

    def _chainup_plugins(
        self, func: Callable[..., Awaitable[R]], sig: EndpointSignature[R]
    ) -> Callable[..., Awaitable[R]]:
        seen: set[int] = set()
        for decor in self._props.plugins:
            if (decor_id := id(decor)) in seen:
                continue

            ep_info = EndpointInfo(self._route.graph, func, sig)
            func = decor(ep_info)
            seen.add(decor_id)
        return func

    def _setup(self, sig: EndpointSignature[R], graph: Graph) -> None:
        if self._is_setup:
            raise Exception(f"`setup` is called more than once in {self}")

        self._sig = sig
        self._graph = graph
        self._func = self._chainup_plugins(self._func, self._sig)
        self._injector = Injector(self._sig)

        self._static = sig.static
        self._status_code = sig.status_code
        self._scoped: bool = sig.scoped or self._props.scoped is True
        self._encoder = self._props.encoder or sig.encoder

        self._media_type = sig.media_type

        self._is_setup = True

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
        else:
            try:
                content = self._encoder(raw_return)
            except TypeError as exc:
                raise UnserializableResponseError(raw_return) from exc
            resp = Response(
                content=content,
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
    def __init__(
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
    ):
        super().__init__(middlewares)
        self._path = trim_path(path)
        self._path_regex: Pattern[str] = build_path_regex(self._path)
        self._graph = graph or Graph(self_inject=False)
        self._workers = None
        self._subroutes: list[Self] = []

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def subroutes(self) -> list[Self]:
        return self._subroutes

    @property
    def path(self) -> str:
        return self._path

    @property
    def path_regex(self) -> Pattern[str]:
        return self._path_regex

    def __truediv__(self, path: str) -> "Self":
        return self.sub(path)

    def is_direct_child_of(self, other_path: "Route | str") -> bool:
        if isinstance(other_path, Route):
            return self.is_direct_child_of(other_path._path)

        if not self._path.startswith(other_path):
            return False
        rest = self._path.removeprefix(other_path)
        return rest.count("/") < 2

    def sub(self, path: str) -> Self:
        sub_path = trim_path(path)
        merged_path = merge_path(self._path, sub_path)
        for sub in self._subroutes:
            if sub._path == merged_path:
                return sub
        sub = self.__class__(
            path=merged_path,
            graph=self._graph,
            middlewares=self.middle_factories,
        )
        self._subroutes.append(sub)
        return sub

    def match(self, scope: IScope) -> bool:
        path = scope["path"]
        if not self._path_regex or not (m := self._path_regex.match(path)):
            return False
        scope["path_params"] = m.groupdict()
        return True

    def add_nodes(
        self, *nodes: Union[IDependent[T], tuple[IDependent[T], INodeConfig]]
    ) -> None:
        self._graph.add_nodes(*nodes)

    def factory(self, node: Callable[..., R], **node_config: Unpack[INodeConfig]):
        return self._graph.node(node, **node_config)

    def _setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ) -> None:
        self._graph = graph or self._graph
        self._workers = workers


class Route(RouteBase):
    def __init__(
        self,
        path: str = "",
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        **iprops: Unpack[IEndpointProps],
    ):
        super().__init__(
            path,
            graph=graph,
            middlewares=middlewares,
        )
        self._endpoints: dict[HTTP_METHODS, Endpoint[Any]] = {}
        self._call_stacks: dict[HTTP_METHODS, ASGIApp] = {}

        if iprops:
            self._props = EndpointProps.from_unpack(**iprops)
        else:
            self._props = EndpointProps()

        if self._props.deps:
            self._graph.add_nodes(*self._props.deps)

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
        endpoint = self._call_stacks.get(scope["method"]) or METHOD_NOT_ALLOWED_RESP
        await endpoint(scope, receive, send)

    def _setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ) -> None:
        super()._setup(workers=workers, graph=graph)
        self.endpoint_parser = EndpointParser(self._graph, self._path)

        for method, ep in self._endpoints.items():
            if ep.is_setup:
                continue
            ep_sig = self.endpoint_parser.parse(ep.unwrapped_func)
            ep._setup(ep_sig, self._graph)
            self._call_stacks[method] = self.chainup_middlewares(ep)

        self._is_setup = True

    def get_endpoint(
        self, method_func: HTTP_METHODS | Callable[..., Any]
    ) -> Endpoint[Any]:
        if not self._is_setup:
            self._setup()

        if isinstance(method_func, str):
            methodname = cast(HTTP_METHODS, method_func.upper())
            return self._endpoints[methodname]

        for ep in self._endpoints.values():
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
                new_sub.include_subroutes(sub_sub, parent_prefix=sub._path)
            self._subroutes.append(new_sub)

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
                self, method=method, func=func, props=props, workers=self._workers
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
