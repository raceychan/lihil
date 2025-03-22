import inspect
import traceback
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from inspect import isasyncgenfunction
from pathlib import Path
from typing import Any, AsyncContextManager, Callable, Unpack, overload

from ididi import Graph
from uvicorn import run as uvi_run

from lihil.config import AppConfig, config_from_file
from lihil.constant.resp import NOT_FOUND_RESP, InternalErrorResp, uvicorn_static_resp
from lihil.errors import AppConfiguringError, DuplicatedRouteError, InvalidLifeSpanError
from lihil.interface import ASGIApp, IReceive, IScope, ISend
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.plugins.bus import BusTerminal
from lihil.problems import LIHIL_ERRESP_REGISTRY, collect_problems
from lihil.routing import ASGIBase, Func, IEndPointConfig, Route
from lihil.utils.parse import is_plain_path
from lihil.utils.phasing import encode_json

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


def read_config(
    config_file: str | Path | None, app_config: AppConfig | None
) -> AppConfig:
    if config_file and app_config:
        raise AppConfiguringError(
            "Can't set both config_file and app_config, choose either one of them"
        )
    elif app_config:
        return app_config
    else:
        return config_from_file(config_file)


class Lihil[T](ASGIBase):
    _userls: LifeSpan[T] | None

    def __init__(
        self,
        *,
        routes: list[Route] | None = None,
        app_config: AppConfig | None = None,
        graph: Graph | None = None,
        busterm: BusTerminal | None = None,
        config_file: Path | str | None = None,
        lifespan: LifeSpan[T] | None = None,
    ):
        super().__init__()
        self.app_config = read_config(config_file, app_config)
        self.workers = ThreadPoolExecutor(
            max_workers=self.app_config.max_thread_workers
        )
        self.graph = graph or Graph(self_inject=True, workers=self.workers)
        self.busterm = busterm or BusTerminal()
        self.root = Route("/", graph=self.graph)
        self.routes: list[Route] = [self.root]
        if routes:
            self.include_routes(*routes)

        self._userls = lifespan_wrapper(lifespan)
        self._app_state: T | None = None
        self.call_stack: ASGIApp
        self.err_registry = LIHIL_ERRESP_REGISTRY
        self._static_cache: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        self._generate_doc_route()

    @property
    def static_cache(self):
        return self._static_cache

    @property
    def app_state(self) -> T | None:
        return self._app_state

    async def on_lifespan(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        await receive()

        if self._userls is None:
            self._setup()
            return

        user_ls = self._userls(self)
        try:
            self._setup()
            self._app_state = await user_ls.__aenter__()
            await send({"type": "lifespan.startup.complete"})
        except BaseException:
            exc_text = traceback.format_exc()
            await send({"type": "lifespan.startup.failed", "message": exc_text})
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
            route.setup()

    def _generate_doc_route(self):
        oas_config = self.app_config.oas
        openapi_route = get_openapi_route(
            oas_config, self.routes, self.app_config.version
        )
        doc_route = get_doc_route(oas_config)
        problems = collect_problems()
        problem_route = get_problem_route(oas_config, problems)
        self.include_routes(openapi_route, doc_route, problem_route)

    def sync_deps(self, route: Route):
        self.graph.merge(route.graph)
        self.busterm.include(route.registry)
        route.sync_deps(self.graph, self.busterm)

    def include_routes(self, *routes: Route, __seen__: set[str] | None = None):
        seen = __seen__ or set()
        for route in routes:
            if route.path in seen:
                raise DuplicatedRouteError(route, route)

            self.sync_deps(route)

            if route.path == "/":
                if self.root.endpoints:
                    raise DuplicatedRouteError(route, self.root)
                self.routes[0] = self.root = route
            else:
                if route.is_direct_child_of(self.root):
                    self.root.subroutes.append(route)
                self.routes.append(route)
            seen.add(route.path)
            for sub in route.subroutes:
                self.include_routes(sub, __seen__=seen)

    def static(
        self,
        path: str,
        static_content: Any,
        content_type: str = "text/plain",
        charset: str = "utf-8",
    ) -> None:
        if not is_plain_path(path):
            raise NotImplementedError(
                "staic resource with dynamic route is not supported"
            )
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

        content_resp = uvicorn_static_resp(encoded, content_type, charset)
        self._static_cache[path] = content_resp

    async def call_route(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        for route in self.routes:
            if cache := self._static_cache.get(scope["path"]):
                header, body = cache
                await send(header)
                await send(body)
                return

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
            await self.on_lifespan(scope, receive, send)
            return

        response_started = False

        async def _send(message: dict[str, Any]) -> None:
            nonlocal response_started, send
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        # TODO: solve this with lhl_server, no extra _send needed.
        try:
            await self.call_stack(scope, receive, _send)  # type: ignore
        except Exception:
            if not response_started:
                await InternalErrorResp(scope, receive, send)
            raise

    def sub(self, path: str) -> "Route":
        route = self.root.sub(path)
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
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def get[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def get[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        return self.root.get(func, **epconfig)

    @overload
    def put[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def put[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def put[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.put(func, **epconfig)

    @overload
    def post[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def post[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def post[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.post(func, **epconfig)

    @overload
    def delete[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def delete[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def delete[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.delete(func, **epconfig)

    @overload
    def patch[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def patch[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def patch[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.patch(func, **epconfig)

    @overload
    def head[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def head[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def head[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.head(func, **epconfig)

    @overload
    def options[**P, R](
        self, **epconfig: Unpack[IEndPointConfig]
    ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    @overload
    def options[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    def options[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.options(func, **epconfig)
