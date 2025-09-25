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
        # Native coroutine functions are already awaitable.
        return func

    if isasyncgenfunction(func):
        # Async generator functions should not be executed in a thread.
        # We wrap them in an async function so callers can `await` to obtain
        # the async generator object, and then stream from it.
        @wraps(func)
        async def agen_wrapper(**params: Any) -> T:
            return func(**params)

        return agen_wrapper

    @wraps(func)
    async def dummy(**params: Any) -> T:
        return func(**params)

    @wraps(func)
    async def inner(**params: Any) -> T:
        ctx = copy_context()
        func_call = partial(ctx.run, func, **params)
        # Resolve the running loop at call time to avoid cross-loop issues
        # when the wrapper is created under a different event loop.
        loop = get_running_loop()
        res = await loop.run_in_executor(workers, func_call)
        return cast(T, res)

    # If there is no running loop at wrapper creation (e.g. created in sync context),
    # prefer the non-threaded dummy; otherwise choose based on `threaded` flag.
    try:
        get_running_loop()
        has_loop = True
    except RuntimeError:
        has_loop = False

    if not has_loop:
        return dummy
    return inner if threaded else dummy
