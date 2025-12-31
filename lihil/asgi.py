from concurrent.futures.thread import ThreadPoolExecutor
from typing import Any, Callable, Pattern

from ididi import Graph
from ididi.interfaces import NodeIgnoreConfig
from typing_extensions import Self, cast

from lihil.errors import MiddlewareBuildError
from lihil.interface import IScope, MiddlewareFactory, R
from lihil.interface.asgi import (
    ASGIApp,
    IReceive,
    IScope,
    ISend,
    MiddlewareFactory,
    TApp,
)
from lihil.utils.string import build_path_regex, merge_path, trim_path


class ASGIBase:
    def __init__(self, middlewares: list[MiddlewareFactory[Any]] | None):
        self.middle_factories: list[MiddlewareFactory[Any]] = middlewares or []

    def add_middleware(
        self,
        middleware_factories: (
            MiddlewareFactory[TApp]
            | tuple[MiddlewareFactory[TApp], ...]
            | list[MiddlewareFactory[TApp]]
        ),
    ) -> None:
        """
        Accept one or more factories for ASGI middlewares
        """
        if isinstance(middleware_factories, (tuple, list)):
            middleware_factories = cast(
                list[MiddlewareFactory[TApp]], middleware_factories
            )
            self.middle_factories = list(middleware_factories) + self.middle_factories
        else:
            self.middle_factories.append(middleware_factories)

    def chainup_middlewares(self, tail: ASGIApp) -> ASGIApp:
        # current = problem_solver(tail, self.err_registry)
        current = tail
        for factory in reversed(self.middle_factories):
            try:
                prev = factory(current)
                assert prev is not None
            except Exception as exc:
                raise MiddlewareBuildError(factory) from exc
            current = prev

        return current

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        raise NotImplementedError


class ASGIRoute(ASGIBase):
    def __init__(
        self,
        path: str = "",
        *,
        graph: Graph | None = None,
        middlewares: list[MiddlewareFactory[Any]] | None = None,
        workers: ThreadPoolExecutor | None = None,
    ):
        super().__init__(middlewares)
        self._path = trim_path(path)
        self._path_regex: Pattern[str] = build_path_regex(path=self._path)
        self._graph = graph or Graph(self_inject=False)
        self._workers = workers
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

    def is_direct_child_of(self, other_path: "ASGIRoute | str") -> bool:
        if isinstance(other_path, ASGIRoute):
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
