from typing import Callable

from premier import Throttler
from premier.throttler.handler import AsyncDefaultHandler as AsyncDefaultHandler
from premier.throttler.interface import AsyncThrottleHandler as AsyncThrottleHandler

from lihil.interface import IAsyncFunc, P, R
from lihil.plugins import IEndpointInfo


class PremierPlugin:
    def __init__(self, throttler_: Throttler):
        self.throttler_ = throttler_

    def fix_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return self.throttler_.fixed_window(quota, duration, keymaker=keymaker)(
                ep_info.func
            )

        return inner

    def sliding_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return self.throttler_.sliding_window(quota, duration, keymaker=keymaker)(
                ep_info.func
            )

        return inner

    def leaky_bucket(
        self,
        quota: int,
        duration: int,
        bucket_size: int,
        keymaker: Callable[..., str] | None = None,
    ):

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return self.throttler_.leaky_bucket(
                bucket_size=bucket_size,
                quota=quota,
                duration=duration,
                keymaker=keymaker,
            )(ep_info.func)

        return inner

    def token_bucket(
        self,
        quota: int,
        duration: int,
        keymaker: Callable[..., str] | None = None,
    ):

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return self.throttler_.token_bucket(
                quota=quota,
                duration=duration,
                keymaker=keymaker,
            )(ep_info.func)

        return inner
