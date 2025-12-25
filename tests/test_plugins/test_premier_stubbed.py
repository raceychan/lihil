import asyncio
import importlib
import sys
import types

import pytest


def _stub_premier(monkeypatch):
    throttler_calls: list[tuple[str, tuple, dict]] = []

    class DummyThrottler:
        def __init__(self, *_, **__):
            self.calls = throttler_calls

        def _wrap(self, name, *args, **kwargs):
            def decorator(func):
                async def wrapper(*fargs, **fkwargs):
                    return await func(*fargs, **fkwargs)

                throttler_calls.append((name, args, kwargs))
                return wrapper

            return decorator

        def fixed_window(self, *args, **kwargs):
            return self._wrap("fixed_window", *args, **kwargs)

        def sliding_window(self, *args, **kwargs):
            return self._wrap("sliding_window", *args, **kwargs)

        def leaky_bucket(self, *args, **kwargs):
            return self._wrap("leaky_bucket", *args, **kwargs)

        def token_bucket(self, *args, **kwargs):
            return self._wrap("token_bucket", *args, **kwargs)

    class DummyCache:
        def __init__(self, *_args, **_kwargs):
            self.calls: list[tuple] = []

        def cache(self, **kwargs):
            def decorator(func):
                async def wrapper(*fargs, **fkwargs):
                    self.calls.append(tuple(kwargs.items()))
                    return await func(*fargs, **fkwargs)

                return wrapper

            return decorator

    def retry(**_kwargs):
        def decorator(func):
            async def wrapper(*fargs, **fkwargs):
                return await func(*fargs, **fkwargs)

            return wrapper

        return decorator

    def timeout(_seconds, logger=None):
        def decorator(func):
            async def wrapper(*fargs, **fkwargs):
                return await func(*fargs, **fkwargs)

            return wrapper

        return decorator

    base = types.ModuleType("premier")
    base.Throttler = DummyThrottler

    cache_mod = types.ModuleType("premier.cache")
    cache_mod.Cache = DummyCache

    providers_mod = types.ModuleType("premier.providers")
    providers_mod.AsyncCacheProvider = object
    providers_mod.AsyncInMemoryCache = type("AsyncInMemoryCache", (), {})  # simple stub

    retry_mod = types.ModuleType("premier.retry")
    retry_mod.retry = retry

    throttler_handler = types.ModuleType("premier.throttler.handler")
    throttler_handler.AsyncDefaultHandler = type("AsyncDefaultHandler", (), {})

    throttler_interface = types.ModuleType("premier.throttler.interface")
    throttler_interface.AsyncThrottleHandler = type("AsyncThrottleHandler", (), {})

    timer_interface = types.ModuleType("premier.timer.interface")
    timer_interface.ILogger = type("ILogger", (), {})

    timer_timer = types.ModuleType("premier.timer.timer")
    timer_timer.timeout = timeout

    monkeypatch.delitem(sys.modules, "lihil.plugins.premier", raising=False)
    stubs = {
        "premier": base,
        "premier.cache": cache_mod,
        "premier.providers": providers_mod,
        "premier.retry": retry_mod,
        "premier.throttler.handler": throttler_handler,
        "premier.throttler.interface": throttler_interface,
        "premier.timer.interface": timer_interface,
        "premier.timer.timer": timer_timer,
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)

    import lihil.plugins.premier as premier

    importlib.reload(premier)
    return premier, throttler_calls


def test_premier_plugin_with_stubbed_dependencies(monkeypatch):
    premier, throttler_calls = _stub_premier(monkeypatch)

    async def run():
        plugin = premier.PremierPlugin()

        async def handler():
            return "ok"

        ep_info = types.SimpleNamespace(func=handler)

        assert await plugin.fixed_window(1, 1)(ep_info)() == "ok"
        assert await plugin.sliding_window(2, 3)(ep_info)() == "ok"
        assert await plugin.leaky_bucket(1, 1, 1)(ep_info)() == "ok"
        assert await plugin.token_bucket(1, 1)(ep_info)() == "ok"
        assert await plugin.cache()(ep_info)() == "ok"
        assert await plugin.retry()(ep_info)() == "ok"
        assert await plugin.timeout(1)(ep_info)() == "ok"

    asyncio.run(run())

    called_names = [name for name, *_ in throttler_calls]
    assert {"fixed_window", "sliding_window", "leaky_bucket", "token_bucket"} <= set(
        called_names
    )
