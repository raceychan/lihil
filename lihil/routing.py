from functools import partial
from inspect import isasyncgen, isgenerator
from types import MethodType
from typing import (
    Any,
    Generic,
    Callable,
    Literal,
    Pattern,
    Sequence,
    TypedDict,
    Union,
    cast,
    overload,
)
from typing_extensions import Unpack, Self

from ididi import Graph, INodeConfig
from ididi.graph import Resolver
from ididi.interfaces import IDependent
from msgspec import field
from starlette.responses import StreamingResponse

from lihil.asgi import ASGIBase
from lihil.auth.oauth import AuthBase
from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.ds.resp import StaticResponse
from lihil.interface import (
    P,
    R,
    T,
    HTTP_METHODS,
    ASGIApp,
    Func,
    IReceive,
    IScope,
    ISend,
    MappingLike,
    MiddlewareFactory,
    Record,
)
from lihil.plugins.bus import BusTerminal, Event, EventBus, MessageRegistry
from lihil.problems import DetailBase, InvalidRequestErrors, get_solver
from lihil.signature import EndpointSignature, ParseResult
from lihil.signature.parser import EndpointParser
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


class EndpointProps(Record, kw_only=True):
    errors: tuple[type[DetailBase[Any]], ...] = field(default_factory=tuple)
    to_thread: bool = True
    in_schema: bool = True
    scoped: Literal[True] | None = None
    auth_scheme: AuthBase | None = None
    tags: Sequence[str] | None = None

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
    ):
        self._route = route
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

    def setup(self, sig: EndpointSignature[R]) -> None:
        self._graph = self._route.graph
        self._busterm = self._route.busterm
        self._app_state = self._route.app_state

        self._sig = sig

        self._dep_items = sig.dependencies.items()
        self._states_items = sig.states.items()
        self._static = sig.static
        self._transitive_params = sig.transitive_params

        self._require_body: bool = sig.body_param is not None
        self._status_code = sig.status_code
        self._scoped: bool = sig.scoped or self._props.scoped is True
        self._encoder = sig.return_encoder
        self._media_type = (
            next(iter(sig.return_params.values())).content_type or "application/json"
        )

    def inject_states(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ):
        for name, p in self._states_items:
            ptype = cast(type, p.type_)
            if issubclass(ptype, Request):
                params[name] = request
            elif issubclass(ptype, EventBus):
                bus = self._busterm.create_event_bus(resolver)
                params[name] = bus
            elif issubclass(ptype, Resolver):
                params[name] = resolver
            else:
                if (state := self._app_state) is None:
                    raise ValueError(
                        f"{self} requires state param {name}, but app state is not set"
                    )
                params[name] = state[name]

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
            if self._require_body:
                parsed_result = await self._sig.parse_command(request)
            else:
                parsed_result = self._sig.parse_query(request)

            callbacks = parsed_result.callbacks
            if errors := parsed_result.errors:
                raise InvalidRequestErrors(detail=errors)

            params = parsed_result.params

            if self._states_items:
                self.inject_states(params, request, resolver)

            for name, dep in self._dep_items:
                params[name] = await resolver.aresolve(dep.dependent, **params)

            for p in self._transitive_params:
                params.pop(p)

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
        registry: MessageRegistry | None = None,
        listeners: list[Callable[..., Any]] | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
    ):
        super().__init__(middlewares)
        self.path = trim_path(path)
        self.path_regex: Pattern[str] | None = None
        self.graph = graph or Graph(self_inject=False)
        self.registry = registry or MessageRegistry(event_base=Event, graph=graph)
        if listeners:
            self.registry.register(*listeners)
        self.busterm = BusTerminal(self.registry, graph=graph)
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

    def sub(self, path: str) -> "Self":
        sub_path = trim_path(path)
        merged_path = merge_path(self.path, sub_path)
        for sub in self.subroutes:
            if sub.path == merged_path:
                return sub
        sub = self.__class__(
            path=merged_path,
            graph=self.graph,
            registry=self.registry,
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

    def listen(self, listener: Callable[[Event, Any], None]) -> None:
        self.registry.register(listener)

    def has_listener(self, listener: Callable[..., Any]) -> bool:
        event_metas = list(self.registry.event_mapping.values())

        for metas in event_metas:
            for meta in metas:
                if meta.handler is listener:
                    return True
        return False

    def setup(
        self,
        graph: Graph | None = None,
        busterm: BusTerminal | None = None,
        app_state: MappingLike | None = None,
    ):
        self.app_state = app_state
        self.graph = graph or self.graph
        self.busterm = busterm or self.busterm


class Route(RouteBase):

    def __init__(  # type: ignore
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        registry: MessageRegistry | None = None,
        listeners: list[Callable[..., Any]] | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        props: EndpointProps | None = None,
    ):
        super().__init__(
            path,
            graph=graph,
            registry=registry,
            listeners=listeners,
            middlewares=middlewares,
        )
        self.endpoints: dict[HTTP_METHODS, Endpoint[Any]] = {}
        self.call_stacks: dict[HTTP_METHODS, ASGIApp] = {}
        self.props = props or EndpointProps(tags=[generate_route_tag(self.path)])

    def __repr__(self):
        endpoints_repr = "".join(
            f", {method}: {endpoint.unwrapped_func}"
            for method, endpoint in self.endpoints.items()
        )
        return f"{self.__class__.__name__}({self.path!r}{endpoints_repr})"

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        endpoint = self.call_stacks.get(scope["method"]) or METHOD_NOT_ALLOWED_RESP
        await endpoint(scope, receive, send)

    def setup(
        self,
        graph: Graph | None = None,
        busterm: BusTerminal | None = None,
        app_state: MappingLike | None = None,
    ):
        super().setup(app_state=app_state, graph=graph, busterm=busterm)
        self.endpoint_parser = EndpointParser(self.graph, self.path)

        for method, ep in self.endpoints.items():
            ep_sig = self.endpoint_parser.parse(ep.unwrapped_func)
            ep.setup(ep_sig)
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
                self,
                method=method,
                func=func,
                props=props,
            )
            self.endpoints[method] = endpoint
            if self.path_regex is None:
                self.path_regex = build_path_regex(self.path)
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
