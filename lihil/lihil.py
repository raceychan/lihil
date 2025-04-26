import inspect
import sys
import traceback
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from inspect import isasyncgenfunction
from pathlib import Path
from typing import Any, AsyncContextManager, Callable, Unpack, cast, overload

from ididi import Graph
from uvicorn import run as uvi_run

from lihil.config import AppConfig, lhl_get_config, lhl_set_config
from lihil.constant.resp import NOT_FOUND_RESP, InternalErrorResp, uvicorn_static_resp
from lihil.errors import DuplicatedRouteError, InvalidLifeSpanError, NotSupportedError
from lihil.interface import ASGIApp, IReceive, IScope, ISend, MiddlewareFactory
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.plugins.bus import BusTerminal
from lihil.problems import LIHIL_ERRESP_REGISTRY, collect_problems
from lihil.routing import (
    ASGIBase,
    EndpointProps,
    Func,
    IEndpointProps,
    Route,
    RouteBase,
)
from lihil.signature.params import LIHIL_PRIMITIVES
from lihil.utils.json import encode_json
from lihil.utils.string import is_plain_path
from lihil.websocket import WebSocketRoute

type LifeSpan[T] = Callable[["Lihil[Any]"], AsyncContextManager[T]]


def lifespan_wrapper[T](lifespan: LifeSpan[T] | None) -> LifeSpan[T] | None:
    if lifespan is None:
        return None
    if isasyncgenfunction(lifespan):
        return asynccontextmanager(lifespan)
    elif (wrapped := getattr(lifespan, "__wrapped__", None)) and isasyncgenfunction(
        wrapped
    ):
        return lifespan
    else:
        raise InvalidLifeSpanError(f"expecting an AsyncContextManager")


StaticCache = dict[str, tuple[dict[str, Any], dict[str, Any]]]


class StaticRoute:
    def __init__(self):
        # TODO: make this a response instead of a route, cancel static route
        # as route gets more complicated this is hard to maintain.
        self.static_cache: StaticCache = {}
        self.path = "_static_route_"
        self.config = EndpointProps(in_schema=False)

    def match(self, scope: IScope) -> bool:
        return scope["path"] in self.static_cache

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend):
        header, body = self.static_cache[scope["path"]]
        await send(header)
        await send(body)

    def add_cache(self, path: str, content: tuple[dict[str, bytes], dict[str, bytes]]):
        self.static_cache[sys.intern(path)] = content

    def setup(self, **deps: Any):
        pass


class Lihil[T](ASGIBase):
    _userls: LifeSpan[T] | None

    def __init__(
        self,
        *,
        routes: list[RouteBase] | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        app_config: AppConfig | None = None,
        graph: Graph | None = None,
        busterm: BusTerminal | None = None,
        config_file: Path | str | None = None,
        lifespan: LifeSpan[T] | None = None,
    ):
        super().__init__(middlewares)
        lhl_set_config(config_file, app_config)
        self.app_config = lhl_get_config()

        self.workers = ThreadPoolExecutor(
            max_workers=self.app_config.max_thread_workers
        )
        self.graph = graph or Graph(
            self_inject=True, workers=self.workers, ignore=LIHIL_PRIMITIVES
        )
        self.busterm = busterm or BusTerminal()
        # =========== keep above order ============
        self.routes: list[RouteBase] = []

        if routes:
            if not any(route.path == "/" for route in routes):
                self.root = Route("/", graph=self.graph)
                self.routes.insert(0, self.root)
            self.include_routes(*routes)
        else:
            self.root = Route("/", graph=self.graph)
            self.routes.insert(0, self.root)

        self._userls = lifespan_wrapper(lifespan)
        self.static_route: StaticRoute | None = None
        self._app_state: T | None = None
        self.call_stack: ASGIApp
        self.err_registry = LIHIL_ERRESP_REGISTRY
        self._generate_builtin_routes()

    def __repr__(self) -> str:
        conn_info = ""
        host, port = self.app_config.server.host, self.app_config.server.port
        if host and port:
            conn_info += f"({host}:{port})"
        lhl_repr = f"{self.__class__.__name__}{conn_info}[\n  "
        routes_repr = "\n  ".join(r.__repr__() for r in self.routes)
        return lhl_repr + routes_repr + "\n]"

    @property
    def app_state(self) -> T | None:
        return self._app_state

    async def _on_lifespan(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        await receive()

        if self._userls is None:
            try:
                self._setup()
            except BaseException:
                exc_text = traceback.format_exc()
                await send({"type": "lifespan.startup.failed", "message": exc_text})
                raise
            else:
                await send({"type": "lifespan.startup.complete"})

            await receive()
            await send({"type": "lifespan.shutdown.complete"})

        else:
            user_ls = self._userls(self)
            try:
                self._app_state = await user_ls.__aenter__()
                self._setup()
            except BaseException:
                exc_text = traceback.format_exc()
                await send({"type": "lifespan.startup.failed", "message": exc_text})
            else:
                await send({"type": "lifespan.startup.complete"})

            await receive()

            try:
                await user_ls.__aexit__(None, None, None)
            except BaseException:
                exc_text = traceback.format_exc()
                await send({"type": "lifespan.shutdown.failed", "message": exc_text})
                raise
            else:
                await send({"type": "lifespan.shutdown.complete"})

    def _setup(self) -> None:
        self.call_stack = self.chainup_middlewares(self.call_route)

        for route in self.routes:
            route.setup(graph=self.graph, busterm=self.busterm)

    def _generate_builtin_routes(self):
        oas_config = self.app_config.oas
        openapi_route = get_openapi_route(
            oas_config, self.routes, self.app_config.version
        )
        doc_route = get_doc_route(oas_config)
        problems = collect_problems()
        problem_route = get_problem_route(oas_config, problems)
        self.include_routes(openapi_route, doc_route, problem_route)

    def _merge_deps(self, route: RouteBase):
        self.graph.merge(route.graph)
        self.busterm.include(route.registry)

    def include_routes(self, *routes: RouteBase, __seen__: set[str] | None = None):
        seen = __seen__ or set()
        for route in routes:
            if route.path in seen:
                raise DuplicatedRouteError(route, route)

            self._merge_deps(route)
            if route.path == "/":
                if self.routes:
                    if isinstance(self.root, Route) and self.root.endpoints:
                        raise DuplicatedRouteError(route, self.root)
                self.root = route
                self.routes.insert(0, self.root)
            else:
                self.routes.append(route)

            seen.add(route.path)
            for sub in route.subroutes:
                if sub.path in seen:
                    continue
                self.include_routes(sub, __seen__=seen)

    def static(
        self,
        path: str,
        static_content: str | bytes | Callable[..., str | bytes | dict[str, Any]],
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
                encoded = encode_json(static_content)

        content_resp = uvicorn_static_resp(encoded, 200, content_type, charset)
        if self.static_route is None:
            self.static_route = StaticRoute()
            self.routes.insert(1, self.static_route)
        self.static_route.add_cache(path, content_resp)

    async def call_route(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        for route in self.routes:
            if route.match(scope):
                return await route(scope, receive, send)
        else:
            return await NOT_FOUND_RESP(scope, receive, send)

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
            await self.call_stack(scope, receive, _send)  # type: ignore
        except Exception:
            if not response_started:
                await InternalErrorResp(scope, receive, send)
            raise

    def sub(self, path: str) -> "RouteBase":
        route = self.root.sub(path)
        if route not in self.routes:
            self.routes.append(route)
        return route

    def run(self, file_path: str, runner: Callable[..., None] = uvi_run):
        """
        app = Lihil()
        app.run(__file__)
        """

        server_config = self.app_config.server
        set_values = {k: v for k, v in server_config.asdict().items() if v is not None}

        worker_num = server_config.workers

        use_app_str = (worker_num and worker_num > 1) or server_config.reload
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
    def get[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def get[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def get[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        assert isinstance(self.root, Route)
        return self.root.get(func, **epconfig)

    @overload
    def put[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def put[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def put[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        assert isinstance(self.root, Route)
        return self.root.put(func, **epconfig)

    @overload
    def post[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def post[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def post[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self.root).post(func, **epconfig)

    @overload
    def delete[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def delete[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def delete[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self.root).delete(func, **epconfig)

    @overload
    def patch[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def patch[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def patch[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self.root).patch(func, **epconfig)

    @overload
    def head[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def head[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def head[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self.root).head(func, **epconfig)

    @overload
    def options[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def options[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def options[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self.root).options(func, **epconfig)

    @overload
    def trace[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def trace[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def trace[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self.root).trace(func, **epconfig)

    @overload
    def connect[**P, R](
        self, **epconfig: Unpack[IEndpointProps]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def connect[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def connect[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndpointProps]
    ) -> Func[P, R]:
        return cast(Route, self.root).connect(func, **epconfig)
