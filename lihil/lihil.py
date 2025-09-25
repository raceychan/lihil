import inspect
import sys
import traceback
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from inspect import isasyncgenfunction
from pathlib import Path
from types import MappingProxyType
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Awaitable,
    Callable,
    Mapping,
    cast,
    final,
    overload,
)

from ididi import Graph
from typing_extensions import Unpack
from uvicorn import run as uvi_run

from lihil.config import IAppConfig, lhl_get_config, lhl_read_config, lhl_set_config
from lihil.constant.resp import NOT_FOUND_RESP, InternalErrorResp, uvicorn_static_resp
from lihil.errors import (
    AppConfiguringError,
    DuplicatedRouteError,
    InvalidLifeSpanError,
    NotSupportedError,
)
from lihil.interface import ASGIApp, IReceive, IScope, ISend, MiddlewareFactory, P, R
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.oas.model import OpenAPI
from lihil.oas.schema import generate_oas
from lihil.problems import LIHIL_ERRESP_REGISTRY, collect_problems
from lihil.routing import (
    ASGIBase,
    EndpointProps,
    Func,
    IEndpointProps,
    Route,
    RouteBase,
)
from lihil.signature.parser import LIHIL_PRIMITIVES
from lihil.utils.json import encoder_factory
from lihil.utils.string import is_plain_path

LifeSpan = Callable[["Lihil"], AsyncContextManager[None] | AsyncGenerator[None, None]]
WrappedLifeSpan = Callable[["Lihil"], AsyncContextManager[None]]


def lifespan_wrapper(ls: LifeSpan | None) -> WrappedLifeSpan | None:
    if ls is None:
        return None
    if isasyncgenfunction(ls):
        return asynccontextmanager(ls)
    elif (wrapped := getattr(ls, "__wrapped__", None)) and isasyncgenfunction(wrapped):
        return cast(WrappedLifeSpan, ls)
    else:
        raise InvalidLifeSpanError(f"expecting an AsyncContextManager")


StaticCache = dict[str, tuple[dict[str, Any], dict[str, Any]]]


class StaticRoute(RouteBase):
    def __init__(self):
        # TODO: make this a response instead of a route, cancel static route
        # as route gets more complicated this is hard to maintain.
        self.static_cache: StaticCache = {}
        self._path = "_static_route_"
        self.config = EndpointProps(in_schema=False)

    def match(self, scope: IScope):
        return scope["path"] in self.static_cache

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend):
        header, body = self.static_cache[scope["path"]]
        await send(header)
        await send(body)

    def add_cache(self, path: str, content: tuple[dict[str, bytes], dict[str, bytes]]):
        self.static_cache[sys.intern(path)] = content


@final
class Lihil(ASGIBase):
    _userls: WrappedLifeSpan | None

    def __init__(
        self,
        *routes: RouteBase,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        app_config: IAppConfig | None = None,
        max_thread_workers: int | None = None,
        graph: Graph | None = None,
        lifespan: LifeSpan | None = None,
    ):
        super().__init__(middlewares)
        _config = app_config or lhl_read_config() or lhl_get_config()
        lhl_set_config(_config)
        self._workers = ThreadPoolExecutor(max_workers=max_thread_workers)
        self._graph = graph or Graph(
            self_inject=True, workers=self._workers, ignore=LIHIL_PRIMITIVES
        )
        self._graph.register_singleton(self.config, IAppConfig)
        # =========== keep above order ============
        self._routes: list[RouteBase] = []
        self._init_routes(routes)
        self._userls = lifespan_wrapper(lifespan)
        self._static_route: StaticRoute | None = None
        self._call_stack: ASGIApp
        self._err_registry = LIHIL_ERRESP_REGISTRY
        self._is_setup: bool = False

    def _init_routes(self, routes: tuple[RouteBase, ...]) -> None:
        if not routes:
            self._root = Route(graph=self._graph)
            self._routes.insert(0, self._root)
        else:
            for route in routes:
                if route.path == "/":
                    self._root = route
                    self.include_routes(route)
                    self._routes.insert(0, self._root)

            self.include_routes(*routes)

    def __repr__(self) -> str:
        config = lhl_get_config()
        conn_info = f"({config.server.HOST}:{config.server.PORT})"
        lhl_repr = f"{self.__class__.__name__}{conn_info}[\n  "
        routes_repr = "\n  ".join(r.__repr__() for r in self._routes)
        return lhl_repr + routes_repr + "\n]"

    @property
    def root(self) -> RouteBase:
        return self._root

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def routes(self) -> list[RouteBase]:
        return self._routes

    @property
    def config(self) -> IAppConfig:
        return lhl_get_config()

    @config.setter
    def config(self, config_val: IAppConfig | None) -> None:
        if config_val is None:
            raise AppConfiguringError(f"Invalid app config {config_val}")
        lhl_set_config(config_val)

    @asynccontextmanager
    async def _lifespan(self):
        if self._userls is None:
            self._setup()
            yield
        else:
            async with self._userls(self):
                self._setup()
                yield

    async def _on_lifespan(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        async def event_handler(event_coro: Awaitable[None | bool], event: str):
            try:
                await event_coro
            except BaseException:
                exc_text = traceback.format_exc()
                await send({"type": f"lifespan.{event}.failed", "message": exc_text})
                raise
            else:
                await send({"type": f"lifespan.{event}.complete"})

        ls = self._lifespan()

        await receive()  # receive {'type': 'lifespan.startup'}
        await event_handler(ls.__aenter__(), "startup")
        await receive()  # receive {'type': 'lifespan.shutdown'}
        await event_handler(ls.__aexit__(None, None, None), "shutdown")

    async def _call_route(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        for route in self._routes:
            if route.match(scope):
                return await route(scope, receive, send)
        else:
            return await NOT_FOUND_RESP(scope, receive, send)

    def _setup(self) -> None:
        self._call_stack = self.chainup_middlewares(self._call_route)
        self._routes.extend(self._generate_builtin_routes())

        for route in self._routes:
            route._setup(graph=self._graph, workers=self._workers)  # type: ignore

        self._is_setup = True

    def _generate_builtin_routes(self) -> tuple[RouteBase, ...]:
        app_config = lhl_get_config()
        oas_config = app_config.oas

        openapi_route = get_openapi_route(
            routes=self._routes,
            oas_config=oas_config,
            app_version=app_config.VERSION,
        )
        doc_route = get_doc_route(oas_config)
        problem_route = get_problem_route(oas_config, collect_problems())

        return (openapi_route, doc_route, problem_route)

    def get_route(self, path: str) -> RouteBase | None:
        for route in self._routes:
            if route.path == path:
                return route

    def genereate_oas(self) -> OpenAPI:
        if not self._is_setup:
            self._setup()

        config = self.config
        return generate_oas(
            routes=self._routes,
            oas_config=config.oas,
            app_version=config.VERSION,
        )

    def include_routes(self, *routes: RouteBase) -> None:
        for route in routes:
            if route in self._routes:
                continue

            self._graph.merge(route.graph)
            if route.path == "/" and route is not self._root:
                if isinstance(self._root, Route) and self._root.endpoints:
                    raise DuplicatedRouteError(route, self._root)
                root_idx = self._routes.index(self._root)
                self._root = self._routes[root_idx] = route
            else:
                self._routes.append(route)

            for sub in route.subroutes:
                self.include_routes(sub)

    def static(
        self,
        path: str,
        static_content: (
            str | bytes | dict[str, Any] | Callable[..., str | bytes | dict[str, Any]]
        ),
        content_type: str = "text/plain",
        charset: str = "utf-8",
    ) -> None:
        if not is_plain_path(path):
            raise NotSupportedError("staic resource with dynamic path is not supported")

        if isinstance(static_content, Callable):
            static_content = static_content()
        elif isinstance(static_content, str):
            static_content = static_content.encode()

        if isinstance(static_content, bytes):
            encoded = static_content
        else:
            if isinstance(static_content, str) and content_type == "text/plain":
                encoded = static_content.encode(charset)
            else:
                encoded = encoder_factory()(static_content)  # type: ignore

        content_resp = uvicorn_static_resp(encoded, 200, content_type, charset)
        if self._static_route is None:
            self._static_route = StaticRoute()
            self._routes.insert(1, self._static_route)
        self._static_route.add_cache(path, content_resp)

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        """
        async def __call__(self, ctx: ConnecitonContext, chan: Channel)
            await channel.receive
        """
        if scope["type"] == "lifespan":
            await self._on_lifespan(scope, receive, send)
            return

        response_started = False

        async def _send(message: dict[str, Any]) -> None:
            nonlocal response_started, send
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._call_stack(scope, receive, _send)  # type: ignore
        except Exception:
            if not response_started:
                await InternalErrorResp(scope, receive, send)
            raise

    def sub(self, path: str) -> "RouteBase":
        route = self._root.sub(path)
        if route not in self._routes:
            self._routes.append(route)
        return route

    def run(self, file_path: str, runner: Callable[..., None] = uvi_run) -> None:
        """
        ```python
        app = Lihil()
        app.run(__file__)
        ```
        """

        config = lhl_get_config()
        server_config = config.server
        set_values = {
            k.lower(): v for k, v in server_config.asdict().items() if v is not None
        }

        worker_num = server_config.WORKERS

        use_app_str = (worker_num and worker_num > 1) or server_config.RELOAD
        if not use_app_str:
            runner(self, **set_values)
            return

        crf = inspect.currentframe()
        assert crf
        caller_frame = crf.f_back
        assert caller_frame
        code_ctx = inspect.getframeinfo(caller_frame).code_context
        assert code_ctx

        caller_source = code_ctx[0].strip()
        instance_name, *_ = caller_source.split(".")

        modname = Path(file_path).stem
        app_str = f"{modname}:{instance_name}"

        runner(app_str, **set_values)

    # ============ Http Methods ================

    @overload
    def get(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def get(self, func: Func[P, R]) -> Func[P, R]: ...

    def get(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        assert isinstance(self._root, Route)
        return self._root.get(func, **epconfig)

    @overload
    def put(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def put(self, func: Func[P, R]) -> Func[P, R]: ...

    def put(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        assert isinstance(self._root, Route)
        return self._root.put(func, **epconfig)

    @overload
    def post(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def post(self, func: Func[P, R]) -> Func[P, R]: ...

    def post(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self._root).post(func, **epconfig)

    @overload
    def delete(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def delete(self, func: Func[P, R]) -> Func[P, R]: ...

    def delete(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self._root).delete(func, **epconfig)

    @overload
    def patch(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def patch(self, func: Func[P, R]) -> Func[P, R]: ...

    def patch(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self._root).patch(func, **epconfig)

    @overload
    def head(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def head(self, func: Func[P, R]) -> Func[P, R]: ...

    def head(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self._root).head(func, **epconfig)

    @overload
    def options(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def options(self, func: Func[P, R]) -> Func[P, R]: ...

    def options(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self._root).options(func, **epconfig)

    @overload
    def trace(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def trace(self, func: Func[P, R]) -> Func[P, R]: ...

    def trace(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self._root).trace(func, **epconfig)

    @overload
    def connect(
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def connect(self, func: Func[P, R]) -> Func[P, R]: ...

    def connect(
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self._root).connect(func, **epconfig)
