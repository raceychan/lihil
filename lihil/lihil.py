import traceback
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from inspect import isasyncgenfunction
from typing import Any, AsyncContextManager, Callable, Sequence, Unpack

from ididi import Graph
from loguru import logger

from lihil.config import AppConfig
from lihil.constant.resp import NOT_FOUND_RESP, generate_static_resp
from lihil.errors import DuplicatedRouteError, InvalidLifeSpanError
from lihil.interface import ASGIApp, Base, IReceive, IScope, ISend, MiddlewareFactory
from lihil.middlewares import last_defense, problem_solver
from lihil.oas import get_doc_route, get_openapi_route, get_problem_route
from lihil.problems import LIHIL_ERRESP_REGISTRY, collect_problems
from lihil.routing import Func, IEndPointConfig, Route
from lihil.utils.parse import is_plain_path
from lihil.utils.phasing import encode_json

# from lihil.vendor_types import Lifespan


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


class AppState(Base): ...


class Lihil[T: AppState]:
    def __init__(
        self,
        graph: Graph | None = None,
        app_config: AppConfig | None = None,
        lifespan: LifeSpan[T] | None = None,
    ):
        self.graph = graph
        self.app_config = app_config or AppConfig()
        self._userls = lifespan_wrapper(lifespan)
        self._app_state: T

        self.workers = ThreadPoolExecutor()
        self.root = Route("/", graph=graph)
        self.routes: list[Route] = [self.root]
        self.middle_factories: list[MiddlewareFactory[Any]] = []
        self.call_stack: ASGIApp | None = None
        self.err_registry = LIHIL_ERRESP_REGISTRY
        # self.bus = MessageBus(graph)
        self._static_cache: dict[str, bytes] = {}
        self._generate_doc_route()

    @property
    def static_cache(self):
        return self._static_cache

    @property
    def app_state(self) -> T:
        return self._app_state

    async def lifespan(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        # chainup app here
        await receive()
        if not self._userls:
            return

        user_ls = self._userls(self)

        try:
            app_state = await user_ls.__aenter__()
            await send({"type": "lifespan.startup.complete"})
        except BaseException:
            exc_text = traceback.format_exc()
            await send({"type": "lifespan.startup.failed", "message": exc_text})
        else:
            self._app_state = app_state
        await receive()

        try:
            await user_ls.__aexit__(None, None, None)
        except BaseException:
            exc_text = traceback.format_exc()
            await send({"type": "lifespan.shutdown.failed", "message": exc_text})
            raise
        else:
            await send({"type": "lifespan.shutdown.complete"})

    def _generate_doc_route(self):
        oas_config = self.app_config.oas
        openapi_route = get_openapi_route(
            oas_config, self.routes, self.app_config.version
        )
        doc_route = get_doc_route(oas_config)
        problem_route = get_problem_route(oas_config, collect_problems())
        self.include_routes(openapi_route, doc_route, problem_route)

    def include_routes(self, *routes: Route, __seen__: set[str] | None = None):
        seen = __seen__ or set()
        for route in routes:
            if route.path in seen:
                continue
            if route.path == "/":
                if self.root.endpoints:
                    raise DuplicatedRouteError(route, self.root)
                self.root = route
                self.routes[0] = route
            else:
                if route.is_direct_child_of(self.root):
                    self.root.subs.append(route)
                self.routes.append(route)
            seen.add(route.path)
            for sub in route.subs:
                self.include_routes(sub, __seen__=seen)

    def static(
        self,
        path: str,
        static_content: Any,
        content_type: str = "text/plain",
        charset: str = "utf-8",
    ):
        if not is_plain_path(path):
            raise NotImplementedError
        if isinstance(static_content, Callable):
            static_content = static_content()
        elif isinstance(static_content, str):
            static_content = static_content.encode()

        if isinstance(static_content, bytes):
            encoded = static_content
        else:
            encoded = encode_json(static_content)

        content_resp = generate_static_resp(encoded, content_type, charset)
        self._static_cache[path] = content_resp

    async def call_route(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        for route in self.routes:
            if not route.match(scope):
                continue
            return await route(scope, receive, send)
        else:
            return await NOT_FOUND_RESP(scope, receive, send)

    def chainup_middlewares(self, tail: ASGIApp) -> ASGIApp:
        current = problem_solver(tail, self.err_registry)
        for factory in reversed(self.middle_factories):
            try:
                prev = factory(current)
            except Exception as exc:
                logger.error(exc)
                raise
            current = prev
        return last_defense(current)

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
            return

        if self.call_stack is None:
            self.call_stack = self.chainup_middlewares(self.call_route)
        await self.call_stack(scope, receive, send)

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
