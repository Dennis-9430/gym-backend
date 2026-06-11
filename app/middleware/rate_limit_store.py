"""Rate limit storage abstraction — supports in-memory sliding window."""
from abc import ABC, abstractmethod
from collections import defaultdict, deque
import time
from typing import Dict, Tuple


class RateLimitStore(ABC):
    """Abstract rate limit storage. Implementations: MemoryStore, RedisStore."""

    @abstractmethod
    async def check_and_increment(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """Check if under limit and increment. Returns (allowed, current_count)."""
        ...


class SlidingWindowMemoryStore(RateLimitStore):
    """In-memory sliding window using deque of timestamps per key."""

    def __init__(self):
        self._store: Dict[str, deque] = defaultdict(deque)

    async def check_and_increment(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        now = time.time()
        window = self._store[key]

        # Clean old entries outside the window
        while window and window[0] < now - window_seconds:
            window.popleft()

        count = len(window)
        if count >= limit:
            return (False, count)

        window.append(now)
        return (True, count + 1)

    async def cleanup_old_keys(self, max_age_seconds: int = 3600):
        """Remove keys that haven't been touched in max_age_seconds."""
        now = time.time()
        to_delete = []
        for key, window in self._store.items():
            while window and window[0] < now - max_age_seconds:
                window.popleft()
            if not window:
                to_delete.append(key)
        for key in to_delete:
            del self._store[key]


class RedisRateLimitStore(RateLimitStore):
    """Redis-backed sliding window rate limit store.

    Requires REDIS_URL and REDIS_RATE_LIMIT_ENABLED=True in settings.
    Falls back to MemoryStore if Redis is not configured.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    async def check_and_increment(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        r = await self._get_redis()
        now = time.time()
        window_key = f"ratelimit:{key}"

        # Remove old entries
        await r.zremrangebyscore(window_key, 0, now - window_seconds)

        # Count current entries
        count = await r.zcard(window_key)

        if count >= limit:
            return (False, count)

        # Add current request
        await r.zadd(window_key, {str(now + id(key)): now})  # unique member
        await r.expire(window_key, window_seconds * 2)

        return (True, count + 1)
