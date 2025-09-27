from typing import Awaitable, Callable

from lihil.errors import MissingDependencyError
from lihil.interface import IAsyncFunc, P, R
from lihil.plugins import IEndpointInfo

try:
    from premier import Throttler
    from premier.cache import Cache
    from premier.providers import AsyncCacheProvider, AsyncInMemoryCache
    from premier.retry import retry
    from premier.throttler.handler import AsyncDefaultHandler as AsyncDefaultHandler
    from premier.throttler.interface import AsyncThrottleHandler as AsyncThrottleHandler
    from premier.timer.interface import ILogger
    from premier.timer.timer import timeout
except ImportError:
    raise MissingDependencyError("premier")


class PremierPlugin:
    """
    Premier plugin for Lihil providing throttling, caching, retry, and timeout functionality.

    This plugin integrates Premier's rate limiting, caching, retry mechanisms, and timeout
    controls with Lihil's endpoint system.

    Args:
        throttler_: Premier Throttler instance for rate limiting
        cache_provider: Cache provider (defaults to AsyncInMemoryCache)

    Example:
        Basic usage with default memory cache:
        ```python
        from lihil.plugins.premier import PremierPlugin
        from premier import Throttler

        plugin = PremierPlugin(Throttler())

        # Apply rate limiting: 10 requests per 60 seconds
        @plugin.fixed_window(10, 60)
        async def api_call():
            return "result"

        # Add caching with 5-minute TTL
        @plugin.cache(expire_s=300)
        async def expensive_operation():
            return "computed result"

        # Add retry with exponential backoff
        @plugin.retry(max_attempts=3, wait=[1, 2, 4])
        async def flaky_service():
            return "service result"

        # Add timeout protection
        @plugin.timeout(30)  # 30 seconds
        async def slow_operation():
            return "slow result"
        ```

        Advanced usage with custom cache provider:
        ```python
        from premier.providers import AsyncInMemoryCache

        custom_cache = AsyncInMemoryCache()
        plugin = PremierPlugin(Throttler(), cache_provider=custom_cache)
        ```

        Combining multiple features:
        ```python
        # Chain multiple decorators for comprehensive protection
        @plugin.timeout(30)
        @plugin.retry(max_attempts=3, wait=[1, 2, 4])
        @plugin.cache(expire_s=300)
        @plugin.fixed_window(10, 60)
        async def robust_api_call():
            return "protected result"
        ```
    """

    def __init__(
        self,
        *,
        cache_provider: AsyncCacheProvider | None = None,
        throttler: Throttler | None = None,
        cache: Cache | None = None,
    ):

        if cache_provider is None:
            cache_provider = AsyncInMemoryCache()

        self.throttler_ = throttler or Throttler()
        self.cache_ = cache or Cache(cache_provider)

    def fixed_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):
        """
        Apply fixed window rate limiting to an endpoint.

        Args:
            quota: Maximum number of requests allowed
            duration: Time window in seconds
            keymaker: Optional function to generate rate limit keys

        Example:
            ```python
            @plugin.fixed_window(10, 60)  # 10 requests per minute
            async def api_endpoint():
                return "result"
            ```
        """

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return self.throttler_.fixed_window(quota, duration, keymaker=keymaker)(
                ep_info.func
            )

        return inner

    def fix_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):
        """Alias for fixed_window for backward compatibility."""
        return self.fixed_window(quota, duration, keymaker)

    def sliding_window(
        self, quota: int, duration: int, keymaker: Callable[..., str] | None = None
    ):
        """
        Apply sliding window rate limiting to an endpoint.

        Args:
            quota: Maximum number of requests allowed
            duration: Time window in seconds
            keymaker: Optional function to generate rate limit keys

        Example:
            ```python
            @plugin.sliding_window(100, 3600)  # 100 requests per hour
            async def api_endpoint():
                return "result"
            ```
        """

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
        """
        Apply leaky bucket rate limiting to an endpoint.

        Args:
            quota: Request processing rate
            duration: Time window in seconds
            bucket_size: Maximum bucket capacity
            keymaker: Optional function to generate rate limit keys

        Example:
            ```python
            @plugin.leaky_bucket(quota=10, duration=60, bucket_size=20)
            async def smooth_api():
                return "smoothed result"
            ```
        """

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
        """
        Apply token bucket rate limiting to an endpoint.

        Args:
            quota: Token generation rate
            duration: Time window in seconds
            keymaker: Optional function to generate rate limit keys

        Example:
            ```python
            @plugin.token_bucket(quota=50, duration=60)  # 50 tokens per minute
            async def burst_api():
                return "burst result"
            ```
        """

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return self.throttler_.token_bucket(
                quota=quota,
                duration=duration,
                keymaker=keymaker,
            )(ep_info.func)

        return inner

    def cache(
        self,
        expire_s: int | None = None,
        cache_key: str | Callable[..., str] | None = None,
        encoder: Callable[[R], bytes] | None = None,
    ):
        """
        Apply caching to an endpoint.

        Args:
            expire_s: Cache TTL in seconds (None for no expiration)
            cache_key: Cache key string or key generation function
            encoder: Optional function to encode results before caching

        Example:
            ```python
            @plugin.cache(expire_s=300)  # 5-minute cache
            async def expensive_computation():
                return "computed result"

            @plugin.cache(cache_key=lambda user_id: f"user:{user_id}")
            async def get_user(user_id: str):
                return {"id": user_id, "name": "John"}

            @plugin.cache(expire_s=600, encoder=json.dumps)
            async def get_complex_data():
                return {"data": [1, 2, 3]}
            ```
        """

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return self.cache_.cache(
                expire_s=expire_s, cache_key=cache_key, encoder=encoder
            )(ep_info.func)

        return inner

    def retry(
        self,
        max_attempts: int = 3,
        wait: float | int | list[float | int] | Callable[[int], float] = 1,
        exceptions: tuple[type[Exception], ...] = (Exception,),
        on_fail: Callable[P, Awaitable[None]] | None = None,
    ):
        """
        Apply retry logic to an endpoint.

        Args:
            max_attempts: Maximum retry attempts
            wait: Wait strategy - fixed seconds, list of delays, or callable
            exceptions: Exception types to retry on
            on_fail: Optional callback on failure

        Example:
            ```python
            @plugin.retry(max_attempts=3, wait=1)  # Fixed 1s delay
            async def flaky_service():
                return "result"

            @plugin.retry(max_attempts=4, wait=[1, 2, 4, 8])  # Exponential backoff
            async def unreliable_api():
                return "api result"

            @plugin.retry(exceptions=(ConnectionError, TimeoutError))
            async def network_call():
                return "network result"

            async def log_failure(*args, **kwargs):
                print(f"Failed with args: {args}, kwargs: {kwargs}")

            @plugin.retry(max_attempts=3, on_fail=log_failure)
            async def monitored_service():
                return "monitored result"
            ```
        """

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return retry(
                max_attempts=max_attempts,
                wait=wait,
                exceptions=exceptions,
                on_fail=on_fail,
            )(ep_info.func)

        return inner

    def timeout(self, seconds: int, logger: ILogger | None = None):
        """
        Apply timeout protection to an endpoint.

        Args:
            seconds: Timeout duration in seconds
            logger: Optional logger for timeout events

        Example:
            ```python
            @plugin.timeout(30)  # 30-second timeout
            async def slow_operation():
                return "result"

            import logging
            logger = logging.getLogger(__name__)

            @plugin.timeout(10, logger=logger)
            async def monitored_operation():
                return "result"
            ```
        """

        def inner(ep_info: IEndpointInfo[P, R]) -> IAsyncFunc[P, R]:
            return timeout(seconds, logger=logger)(ep_info.func)

        return inner
