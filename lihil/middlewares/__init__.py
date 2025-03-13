from functools import lru_cache
from typing import Any, cast

from starlette.requests import Request

from lihil.constant.resp import InternalErrorResp
from lihil.interface import ASGIApp, IReceive, IScope, ISend
from lihil.problems import DetailBase, ErrorRegistry, ExceptionHandler

"""
TODO: get rid of 
self.app,
do await next(scope, receive, send) instead
we might need to redesign ASGI for this
"""


# TODO: make these two functions


def last_defense(app: ASGIApp):
    async def call(scope: IScope, receive: IReceive, send: ISend):
        try:
            await app(scope, receive, send)
        except Exception as exc:
            await InternalErrorResp(scope, receive, send)
            raise exc

    return call


def problem_solver(app: ASGIApp, registry: ErrorRegistry):
    status_handlers: dict[int, ExceptionHandler[DetailBase[Any]]] = {}
    exc_handlers: dict[type[DetailBase[Any]], ExceptionHandler[DetailBase[Any]]] = {}

    for target, handler in registry.items():
        if isinstance(target, int):
            status_handlers[target] = handler
        else:
            exc_handlers[target] = handler

    @lru_cache
    def get_handler(exc: DetailBase[Any]) -> ExceptionHandler[DetailBase[Any]] | None:
        try:
            code = exc.__status__
            return status_handlers[code]
        except AttributeError:
            pass
        except KeyError:
            pass

        for base in type(exc).__mro__:
            if res := exc_handlers.get(base):
                return res

    async def call(scope: IScope, receive: IReceive, send: ISend):
        try:
            await app(scope, receive, send)
        except Exception as exc:
            exc = cast(DetailBase[str], exc)
            req = Request(scope, receive, send)
            handler = get_handler(exc)
            if not handler:
                raise
            await handler(req, exc)(scope, receive, send)

    return call
