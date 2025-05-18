from premier import throttler

from lihil.plugins import Any, Callable, EndpointSignature, Graph, IFunc


class PremierPlugin:
    def __init__(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):
        self.quota = quota
        self.duration = duration
        self.keymaker = keymaker

    async def fix_window(
        self, graph: Graph, func: IFunc, sig: EndpointSignature[Any]
    ) -> IFunc:
        return throttler.fixed_window(self.quota, self.duration, self.keymaker)(func)
