from lihil.plugins.premier import PremierPlugin
from lihil.plugins.testclient import LocalClient



async def test_throttling():
    async def hello():
        return "hello"


    lc = LocalClient()

    ep = await lc.make_endpoint(hello, plugins=[PremierPlugin(1, 1).fix_window])
