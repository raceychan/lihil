from typing import Any, Sequence

from lihil.interface.asgi import ASGIApp, MiddlewareFactory


class ASGIBase:

    def __init__(self):
        self.middle_factories: list[MiddlewareFactory[Any]] = []

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

    def chainup_middlewares(self, tail: ASGIApp) -> ASGIApp:
        # current = problem_solver(tail, self.err_registry)
        current = tail
        for factory in reversed(self.middle_factories):
            try:
                prev = factory(current)
            except Exception:
                raise
            current = prev
        return current
