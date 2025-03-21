from asyncio import AbstractEventLoop, get_running_loop
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from contextvars import copy_context
from functools import partial, wraps
from inspect import iscoroutinefunction
from typing import Any, AsyncIterator, Awaitable, Callable, ContextManager, cast


@asynccontextmanager
async def sync_ctx_to_thread[T](
    loop: AbstractEventLoop, workers: ThreadPoolExecutor, cm: ContextManager[T]
) -> AsyncIterator[T]:
    exc_type, exc, tb = None, None, None
    ctx = copy_context()
    cm_enter = partial(ctx.run, cm.__enter__)
    cm_exit = partial(ctx.run, cm.__exit__)

    try:
        res = await loop.run_in_executor(workers, cm_enter)
        yield res
    except Exception as e:
        exc_type, exc, tb = type(e), e, e.__traceback__
        raise
    finally:
        await loop.run_in_executor(workers, cm_exit, exc_type, exc, tb)


def async_wrapper[R](
    func: Callable[..., R],
    *,
    threaded: bool = True,
    workers: ThreadPoolExecutor | None = None,
) -> Callable[..., Awaitable[R]]:
    # TODO: use our own Threading workers
    if iscoroutinefunction(func):
        return func

    loop = get_running_loop()

    @wraps(func)
    async def inner(**params: Any) -> R:
        ctx = copy_context()
        func_call = partial(ctx.run, func, **params)
        res = await loop.run_in_executor(workers, func_call)
        return cast(R, res)

    if threaded:
        return inner

    @wraps(func)
    async def dummy(**params: Any) -> R:
        return func(**params)

    return dummy
