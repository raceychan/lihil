import traceback
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from inspect import isasyncgenfunction
from pathlib import Path
from typing import Any, AsyncContextManager, Callable, Sequence, Unpack, cast

from ididi import Graph

from lihil.config import AppConfig
from lihil.constant.resp import NOT_FOUND_RESP, InternalErrorResp, uvicorn_static_resp
from lihil.errors import AppConfiguringError, DuplicatedRouteError, InvalidLifeSpanError
from lihil.interface import ASGIApp, Base, IReceive, IScope, ISend, MiddlewareFactory
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.plugins.bus import Collector
from lihil.problems import LIHIL_ERRESP_REGISTRY, collect_problems
from lihil.routing import Func, IEndPointConfig, Route
from lihil.utils.parse import is_plain_path
from lihil.utils.phasing import encode_json

type LifeSpan[T] = Callable[["Lihil[Any]"], AsyncContextManager[T]]


def lifespan_wrapper[T](lifespan: LifeSpan[T] | None) -> LifeSpan[T] | None:
    if lifespan is None:
        return None

    if (wrapped := getattr(lifespan, "__wrapped__")) and isasyncgenfunction(wrapped):
        return lifespan
    elif isasyncgenfunction(lifespan):
        return asynccontextmanager(lifespan)
    else:
        raise InvalidLifeSpanError(f"expecting an AsyncContextManager")


class AppState(Base):
    # just a typing helper
    ...


class Lihil[T: AppState]:
    _userls: LifeSpan[T] | None

    def __init__(
        self,
        graph: Graph | None = None,
        collector: Collector | None = None,
        app_config: AppConfig | None = None,
        config_file: Path | str | None = None,
        lifespan: LifeSpan[T] | None = None,
    ):
        self.graph = graph or Graph(self_inject=True)

        if config_file and app_config:
            raise AppConfiguringError(
                "Can't set both config_file and app_config, choose either one of them"
            )
        elif app_config:
            self.app_config = app_config
        else:
            self.app_config = AppConfig.from_file(config_file)

        self.app_config = app_config or AppConfig()
        self._userls = lifespan_wrapper(lifespan)
        self._app_state: T | None = None
        self.collector = collector or Collector()

        self.workers = ThreadPoolExecutor()
        self.root = Route("/", graph=self.graph)
        self.routes: list[Route] = [self.root]
        self.middle_factories: list[MiddlewareFactory[Any]] = []
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
        # Todo: chain routes here too
        self.call_stack = self.chainup_middlewares(self.call_route)

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
        self.collector.include(route.registry)

        route.graph = self.graph
        route.collector = self.collector

    def include_routes(self, *routes: Route, __seen__: set[str] | None = None):
        seen = __seen__ or set()
        for route in routes:
            if route.path in seen:
                continue

            self.sync_deps(route)

            if route.path == "/":
                if self.root.endpoints:
                    raise DuplicatedRouteError(route, self.root)
                self.root = route
                self.routes[0] = route
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

    def chainup_middlewares(self, tail: ASGIApp) -> ASGIApp:
        # current = problem_solver(tail, self.err_registry)
        current = tail
        for factory in reversed(self.middle_factories):
            try:
                prev = factory(current)
            except Exception as exc:
                raise
            current = prev
        return current

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

        # TODO: solve this with lhl_server
        try:
            await self.call_stack(scope, receive, cast(ISend, _send))
        except Exception:
            if not response_started:
                await InternalErrorResp(scope, receive, send)
            raise

    def add_middleware[M: ASGIApp](
        self,
        middleware_factories: MiddlewareFactory[M] | Sequence[MiddlewareFactory[M]],
    ) -> None:
        """
        Accept one or more factories for ASGI middlewares
        """
        if isinstance(middleware_factories, Sequence):
            self.middle_factories = list(middleware_factories) + self.middle_factories
        else:
            self.middle_factories.insert(0, middleware_factories)

    def sub(self, path: str) -> "Route":
        route = self.root.sub(path)
        self.routes.append(route)
        return route

    def get[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
        return self.root.get(func, **epconfig)

    def put[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.put(func, **epconfig)

    def post[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.post(func, **epconfig)

    def delete[**P, R](
        self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    ) -> Func[P, R]:
        return self.root.delete(func, **epconfig)
