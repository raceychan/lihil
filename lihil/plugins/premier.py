from premier import Throttler, throttler
from premier.handler import AsyncThrottleHandler as AsyncThrottleHandler

from lihil.plugins import Any, Callable, EndpointSignature, Graph, IFunc


class PremierPlugin:
    def __init__(self, throttler_: Throttler):
        self.throttler_ = throttler_

    def fix_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):

        async def inner(
            graph: Graph, func: IFunc, sig: EndpointSignature[Any]
        ) -> IFunc:
            return self.throttler_.fixed_window(quota, duration)(func)


        return inner
