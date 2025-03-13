from asyncio import AbstractEventLoop
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from contextvars import copy_context
from functools import partial
from typing import AsyncIterator, ContextManager


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
