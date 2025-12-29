import warnings
from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial
from inspect import isasyncgen, isgenerator
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Generic, Pattern, cast, overload

from ididi import Graph
from ididi.graph import Resolver
from ididi.interfaces import NodeIgnoreConfig
from typing_extensions import Self, Unpack

from lihil.asgi import ASGIBase
from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.errors import InvalidEndpointError, LihilError, UnserializableResponseError
from lihil.interface import (
    HTTP_METHODS,
    MISSING,
    ASGIApp,
    Func,
    IAsyncFunc,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    P,
    R,
    Record,
)
from lihil.problems import InvalidFormError, InvalidRequestErrors, get_solver
from lihil.props import EndpointProps, IEndpointProps
from lihil.signature import EndpointParser, EndpointSignature, Injector, ParseResult
from lihil.signature.returns import agen_encode_wrapper, syncgen_encode_wrapper
from lihil.utils.string import (
    build_path_regex,
    generate_route_tag,
    merge_path,
    trim_path,
)
from lihil.utils.threading import async_wrapper
from lihil.vendors import MultiPartException, Request, Response, StreamingResponse


class HTTPInjector(Injector[R]):
    async def validate_request(self, req: Request, resolver: Resolver):
        parsed = self._validate_conn(req)
        params, errors = parsed.params, parsed.errors

        if self.body_param:
            name, param = self.body_param

            if form_meta := self.form_meta:
                try:
                    body = await req.form(
                        max_files=form_meta.max_files,
                        max_fields=form_meta.max_fields,
                        max_part_size=form_meta.max_part_size,
                    )
                except MultiPartException:
                    body = b""
                    errors.append(InvalidFormError("body", name))
                else:
                    parsed.callbacks.append(body.close)
            else:
                body = await req.body()

            val, error = param.extract(body)
            if val is not MISSING:
                params[name] = val
            else:
                errors.append(error)  # type: ignore

        if errors:
            raise InvalidRequestErrors(detail=errors)

        for name, p in self.state_params:
            ptype = p.type_
            if not isinstance(ptype, type):
                continue
            if issubclass(ptype, Request):
                params[name] = req
            elif issubclass(ptype, Resolver):
                params[name] = resolver

        for name, dep in self.deps:
            params[name] = await resolver.aresolve(dep.dependent, **params)

        for p in self.transitive_params:
            params.pop(p)

        return parsed


class EndpointInfo(Record, Generic[P, R]):
    graph: Graph
    func: IAsyncFunc[P, R]
    sig: EndpointSignature[R]


class Endpoint(Generic[R]):
    def __init__(
        self,
        path: str,
        method: HTTP_METHODS,
        func: Callable[..., R],
        props: EndpointProps,
        workers: ThreadPoolExecutor | None,
    ):
        self._path = path
        self._method: HTTP_METHODS = method
        self._unwrapped_func = func
        self._func = async_wrapper(func, threaded=props.to_thread, workers=workers)
        self._props = props
        self._name = func.__name__
        self._is_setup: bool = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._method}: {self._path!r} {self._func})"

    @property
    def props(self) -> EndpointProps:
        return self._props

    @property
    def path(self) -> str:
        return self._path

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
        self, func: Callable[..., Awaitable[R]], sig: EndpointSignature[R], graph: Graph
    ) -> Callable[..., Awaitable[R]]:
        seen: set[int] = set()
        for decor in self._props.plugins:
            if (decor_id := id(decor)) in seen:
                continue

            ep_info = EndpointInfo(graph, func, sig)
            func = decor(ep_info)
            seen.add(decor_id)
        return func

    def setup(self, sig: EndpointSignature[R], graph: Graph) -> None:
        if self._is_setup:
            raise Exception(f"`setup` is called more than once in {self}")

        self._sig = sig
        self._graph = graph
        self._func = self._chainup_plugins(self._func, self._sig, graph)
        self._injector = HTTPInjector(self._sig)

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
        self._path_regex: Pattern[str] = build_path_regex(path=self._path)
        self._graph = graph or Graph(self_inject=False)
        self._workers = None
        self._subroutes: list[Self] = []
        self._is_setup = False

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

    def add_nodes(self, *nodes: Any) -> None:
        self._graph.add_nodes(*nodes)

    def factory(self, node: Callable[..., R], *, ignore: NodeIgnoreConfig = ()):
        return self._graph.node(node, ignore=ignore)

    def setup(
        self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None
    ) -> None:
        self._graph = graph or self._graph
        self._workers = workers
        self._is_setup = True

    @property
    def is_setup(self) -> bool:
        return self._is_setup


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
