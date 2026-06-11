"""Rate limiting middleware with endpoint-specific rules and pluggable storage."""
import logging
import re
from typing import List, Optional, Pattern, Tuple
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.middleware.rate_limit_store import RateLimitStore, SlidingWindowMemoryStore, RedisRateLimitStore

logger = logging.getLogger(__name__)

# Singleton store — shared across instances
_store: Optional[RateLimitStore] = None


def get_store() -> RateLimitStore:
    global _store
    if _store is None:
        if settings.REDIS_RATE_LIMIT_ENABLED and settings.REDIS_URL:
            _store = RedisRateLimitStore(settings.REDIS_URL)
            logger.info("Using RedisRateLimitStore")
        else:
            _store = SlidingWindowMemoryStore()
            logger.info("Using SlidingWindowMemoryStore")
    return _store


def set_store(store: RateLimitStore):
    """Override store (for testing)."""
    global _store
    _store = store


# Default limits
DEFAULT_RATE_LIMIT = 2000  # requests per minute
DEFAULT_WINDOW = 60  # seconds

# Endpoint-specific rules
# Format: (path_pattern, [(identifier_key, limit, window_seconds), ...])
# identifier_key: "ip" for client IP, or a header name
RATE_LIMIT_RULES: List[Tuple[Pattern, List[Tuple[str, int, int]]]] = [
    # Login: 5/min per IP
    (re.compile(r"^/api/tenants/login$"), [("ip", 5, 60)]),
    # Forgot password: 3/hour per IP
    (re.compile(r"^/api/tenants/forgot-password$"), [("ip", 3, 3600)]),
    # Register: 5/hour per IP
    (re.compile(r"^/api/tenants/register$"), [("ip", 5, 3600)]),
    # Reset password: 5/hour per IP
    (re.compile(r"^/api/tenants/reset-password$"), [("ip", 5, 3600)]),
]

EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


def get_client_ip(request: Request) -> str:
    """Get client IP — supports X-Forwarded-For for proxied deployments."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_identifier(request: Request, key: str) -> str:
    """Get identifier value from request.

    Args:
        key: "ip" for client IP, or a header name
    """
    if key == "ip":
        return get_client_ip(request)
    return request.headers.get(key, get_client_ip(request))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with endpoint-specific rules."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in EXEMPT_PATHS:
            return await call_next(request)

        store = get_store()

        # Check endpoint-specific rules first
        for pattern, rules in RATE_LIMIT_RULES:
            if pattern.match(path):
                for identifier_key, limit, window in rules:
                    client_id = get_identifier(request, identifier_key)
                    rule_key = f"{path}:{identifier_key}:{client_id}"
                    allowed, count = await store.check_and_increment(rule_key, limit, window)
                    if not allowed:
                        return JSONResponse(
                            status_code=429,
                            content={"error": {"code": "RATE_LIMITED", "detail": "Demasiadas solicitudes. Intente de nuevo más tarde.", "message": "Demasiadas solicitudes. Intente de nuevo más tarde."}},
                            headers={"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"}
                        )
                break  # matched a rule, don't apply default

        # Default rate limit (applies to all other routes)
        client_ip = get_client_ip(request)
        allowed, count = await store.check_and_increment(
            f"default:{client_ip}", DEFAULT_RATE_LIMIT, DEFAULT_WINDOW
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMITED", "detail": "Demasiadas solicitudes. Intente de nuevo más tarde.", "message": "Demasiadas solicitudes. Intente de nuevo más tarde."}}
            )

        return await call_next(request)
