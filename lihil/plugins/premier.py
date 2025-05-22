from typing import Callable

from premier import Throttler
from premier import throttler as throttler
from premier.handler import AsyncDefaultHandler as AsyncDefaultHandler
from premier.interface import AsyncThrottleHandler as AsyncThrottleHandler

from lihil.interface import IAsyncFunc, P, R
from lihil.plugins import Any, EndpointSignature, Graph, IAsyncFunc


class PremierPlugin:
    def __init__(self, throttler_: Throttler):
        self.throttler_ = throttler_

    def fix_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):

        def inner(
            graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
        ) -> IAsyncFunc[P, R]:
            return self.throttler_.fixed_window(quota, duration, keymaker=keymaker)(
                func
            )

        return inner

    def sliding_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):

        def inner(
            graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
        ) -> IAsyncFunc[P, R]:
            return self.throttler_.sliding_window(quota, duration, keymaker=keymaker)(
                func
            )

        return inner

    def leaky_bucket(
        self,
        quota: int,
        duration: int,
        bucket_size: int,
        keymaker: Callable[..., str] | None = None,
    ):

        def inner(
            graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
        ) -> IAsyncFunc[P, R]:
            return self.throttler_.leaky_bucket(
                bucket_size=bucket_size,
                quota=quota,
                duration=duration,
                keymaker=keymaker,
            )(func)

        return inner

    def token_bucket(
        self,
        quota: int,
        duration: int,
        keymaker: Callable[..., str] | None = None,
    ):

        def inner(
            graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
        ) -> IAsyncFunc[P, R]:
            return self.throttler_.token_bucket(
                quota=quota,
                duration=duration,
                keymaker=keymaker,
            )(func)

        return inner
