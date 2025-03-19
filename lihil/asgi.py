import traceback
from contextlib import asynccontextmanager
from inspect import isasyncgenfunction
from typing import Any, Sequence

from lihil.errors import InvalidLifeSpanError
from lihil.interface import IReceive, IScope, ISend, LifeSpan
from lihil.interface.asgi import ASGIApp, MiddlewareFactory

# from lihil.plugins.bus import Collector


def lifespan_wrapper(lifespan: LifeSpan | None) -> LifeSpan | None:
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


class ASGIBase:
    call_stack: ASGIApp

    def __init__(self, lifespan: LifeSpan | None):
        self.middle_factories: list[MiddlewareFactory[Any]] = []
        self._user_lifespan = lifespan_wrapper(lifespan)

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

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        raise NotImplementedError("To be overriden")

    def _setup(self) -> None: ...

    async def on_lifespan(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        await receive()

        if self._user_lifespan is None:
            self._setup()
            return

        user_ls = self._user_lifespan(self)
        try:
            self._setup()
            await user_ls.__aenter__()
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

    # @overload
    # def get[**P, R](
    #     self, **epconfig: Unpack[IEndPointConfig]
    # ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    # @overload
    # def get[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    # @overload
    # def get[**P, R](
    #     self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]: ...

    # def get[**P, R](
    #     self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
    #     raise NotImplementedError

    # @overload
    # def put[**P, R](
    #     self, **epconfig: Unpack[IEndPointConfig]
    # ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    # @overload
    # def put[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    # @overload
    # def put[**P, R](
    #     self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]: ...

    # def put[**P, R](
    #     self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]:
    #     raise NotImplementedError

    # @overload
    # def post[**P, R](
    #     self, **epconfig: Unpack[IEndPointConfig]
    # ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    # @overload
    # def post[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    # @overload
    # def post[**P, R](
    #     self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]: ...

    # def post[**P, R](
    #     self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]:
    #     raise NotImplementedError

    # @overload
    # def delete[**P, R](
    #     self, **epconfig: Unpack[IEndPointConfig]
    # ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    # @overload
    # def delete[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    # @overload
    # def delete[**P, R](
    #     self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]: ...

    # def delete[**P, R](
    #     self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]:
    #     raise NotImplementedError

    # @overload
    # def patch[**P, R](
    #     self, **epconfig: Unpack[IEndPointConfig]
    # ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    # @overload
    # def patch[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    # @overload
    # def patch[**P, R](
    #     self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]: ...

    # def patch[**P, R](
    #     self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
    #     raise NotImplementedError

    # @overload
    # def head[**P, R](
    #     self, **epconfig: Unpack[IEndPointConfig]
    # ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    # @overload
    # def head[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    # @overload
    # def head[**P, R](
    #     self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]: ...

    # def head[**P, R](
    #     self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R] | Callable[[Func[P, R]], Func[P, R]]:
    #     raise NotImplementedError

    # @overload
    # def options[**P, R](
    #     self, **epconfig: Unpack[IEndPointConfig]
    # ) -> Callable[[Func[P, R]], Func[P, R]]: ...

    # @overload
    # def options[**P, R](self, func: Func[P, R]) -> Func[P, R]: ...

    # @overload
    # def options[**P, R](
    #     self, func: Func[P, R] | None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]: ...

    # def options[**P, R](
    #     self, func: Func[P, R] | None = None, **epconfig: Unpack[IEndPointConfig]
    # ) -> Func[P, R]:
    #     raise NotImplementedError
