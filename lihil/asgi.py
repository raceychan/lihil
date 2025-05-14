from typing import Any, Sequence

from lihil.errors import MiddlewareBuildError
from lihil.interface.asgi import ASGIApp, MiddlewareFactory, TApp


class ASGIBase:

    def __init__(self, middlewares: list[MiddlewareFactory[Any]] | None):
        self.middle_factories: list[MiddlewareFactory[Any]] = middlewares or []

    def add_middleware(
        self,
        middleware_factories: (
            MiddlewareFactory[TApp] | Sequence[MiddlewareFactory[TApp]]
        ),
    ) -> None:
        """
        Accept one or more factories for ASGI middlewares
        """
        if isinstance(middleware_factories, Sequence):
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
