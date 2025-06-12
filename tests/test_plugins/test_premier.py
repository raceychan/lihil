import pytest
from premier.throttler.errors import QuotaExceedsError

from lihil.local_client import LocalClient
from lihil.plugins.premier import PremierPlugin, Throttler


async def test_throttling():
    async def hello():
        print("called the hello func")
        return "hello"

    lc = LocalClient()

    throttler = Throttler()

    plugin = PremierPlugin(throttler)

    ep = await lc.make_endpoint(hello, plugins=[plugin.fix_window(1, 1)])

    await lc(ep)

    with pytest.raises(QuotaExceedsError):
        for _ in range(2):
            await lc(ep)
