"""Fixed-window rate limits.

Fixed windows can admit up to twice the limit across a window boundary. That
is acceptable here: the limits protect capacity and model spend, not money.
"""

import math
import time
from collections.abc import Callable
from typing import Protocol

from redis.asyncio import Redis


class RateLimited(Exception):
    def __init__(self, retry_after: float, what: str) -> None:
        super().__init__(f"rate limit exceeded for {what}; retry after {math.ceil(retry_after)}s")
        self.retry_after = retry_after


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window: int = 60) -> float | None:
        """Count one request. Returns seconds to wait if over the limit, else None."""
        ...

    async def exceeded(self, key: str, limit: int, window: int = 60) -> float | None:
        """Like ``hit`` but does not count."""
        ...


class NoRateLimit:
    async def hit(self, key: str, limit: int, window: int = 60) -> float | None:
        return None

    async def exceeded(self, key: str, limit: int, window: int = 60) -> float | None:
        return None


class MemoryRateLimiter:
    """For a single API process (and tests)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._counts: dict[str, tuple[int, int]] = {}  # key -> (window index, count)

    def _state(self, key: str, window: int) -> tuple[int, int, float]:
        now = self.clock()
        index = int(now // window)
        current, count = self._counts.get(key, (index, 0))
        if current != index:
            count = 0
        return index, count, window - (now % window)

    async def hit(self, key: str, limit: int, window: int = 60) -> float | None:
        index, count, remaining = self._state(key, window)
        if len(self._counts) > 100_000:  # drop stale windows
            self._counts = {k: v for k, v in self._counts.items() if v[0] == index}
        self._counts[key] = (index, count + 1)
        return remaining if count + 1 > limit else None

    async def exceeded(self, key: str, limit: int, window: int = 60) -> float | None:
        _, count, remaining = self._state(key, window)
        return remaining if count >= limit else None


class RedisRateLimiter:
    """Shared counters for several API processes."""

    def __init__(self, redis: Redis, clock: Callable[[], float] = time.time) -> None:
        self.redis, self.clock = redis, clock

    def _key(self, key: str, window: int) -> tuple[str, float]:
        now = self.clock()
        return f"antos:rl:{key}:{int(now // window)}", window - (now % window)

    async def hit(self, key: str, limit: int, window: int = 60) -> float | None:
        name, remaining = self._key(key, window)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(name)
            pipe.expire(name, window + 1)
            count, _ = await pipe.execute()
        return remaining if int(count) > limit else None

    async def exceeded(self, key: str, limit: int, window: int = 60) -> float | None:
        name, remaining = self._key(key, window)
        count = await self.redis.get(name)
        return remaining if count is not None and int(count) >= limit else None
