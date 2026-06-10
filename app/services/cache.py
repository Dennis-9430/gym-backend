"""Simple in-memory TTL cache."""
import time
from typing import Any, Optional, Dict, Tuple


class TTLCache:
    """Simple in-memory cache with TTL."""

    def __init__(self):
        self._store: Dict[str, Tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            value, expiry = self._store[key]
            if time.time() < expiry:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 30):
        self._store[key] = (value, time.time() + ttl_seconds)

    def invalidate(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()


# Singleton
_cache: Optional[TTLCache] = None


def get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache()
    return _cache
