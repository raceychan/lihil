from asyncio import get_running_loop
from concurrent.futures.thread import ThreadPoolExecutor
from contextvars import copy_context
from functools import partial, wraps
from inspect import isasyncgenfunction, iscoroutinefunction
from typing import Any, Awaitable, Callable, TypeVar, cast

T = TypeVar("T")


# @asynccontextmanager
# async def sync_ctx_to_thread(
#     loop: AbstractEventLoop, workers: ThreadPoolExecutor, cm: ContextManager[T]
# ) -> AsyncIterator[T]:
#     exc_type, exc, tb = None, None, None
#     ctx = copy_context()
#     cm_enter = partial(ctx.run, cm.__enter__)
#     cm_exit = partial(ctx.run, cm.__exit__)

#     try:
#         res = await loop.run_in_executor(workers, cm_enter)
#         yield res
#     except Exception as e:
#         exc_type, exc, tb = type(e), e, e.__traceback__
#         raise
#     finally:
#         await loop.run_in_executor(workers, cm_exit, exc_type, exc, tb)


def async_wrapper(
    func: Callable[..., T],
    *,
    threaded: bool = True,
    workers: ThreadPoolExecutor | None = None,
) -> Callable[..., Awaitable[T]]:
    if iscoroutinefunction(func):
        return func

    @wraps(func)
    async def dummy(**params: Any) -> T:
        return func(**params)

    if isasyncgenfunction(func):
        return dummy

    @wraps(func)
    async def inner(**params: Any) -> T:
        ctx = copy_context()
        func_call = partial(ctx.run, func, **params)
        # Resolve the running loop at call time to avoid cross-loop issues
        # when the wrapper is created under a different event loop.
        loop = get_running_loop()
        res = await loop.run_in_executor(workers, func_call)
        return cast(T, res)

    try:
        get_running_loop()
        has_loop = True
    except RuntimeError:
        has_loop = False

    # standard scene, created in async context and user set threaded flag to true
    if has_loop and threaded:
        return inner

    return dummy
