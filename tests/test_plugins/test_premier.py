import pytest
from premier.handler import AsyncDefaultHandler
from premier.errors import QuotaExceedsError

from lihil.plugins.premier import PremierPlugin, throttler
from lihil.local_client import LocalClient


async def test_throttling():
    async def hello():
        print("called the hello func")
        return "hello"

    lc = LocalClient()

    throttler.config(aiohandler=AsyncDefaultHandler())

    plugin = PremierPlugin(throttler)

    ep = await lc.make_endpoint(hello, plugins=[plugin.fix_window(1, 1)])

    await lc(ep)

    with pytest.raises(QuotaExceedsError):
        for _ in range(2):
            await lc(ep)
