"""CSRF Double Submit Cookie middleware"""
import secrets
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_403_FORBIDDEN
from app.config import settings

logger = logging.getLogger(__name__)


class CSRFTokenMiddleware(BaseHTTPMiddleware):
    """CSRF protection via Double Submit Cookie pattern.

    In warn mode (CSRF_ENABLED=False): sets cookie, logs mismatches but doesn't block.
    In enforcement mode (CSRF_ENABLED=True): blocks requests with invalid/missing CSRF token.
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    CSRF_HEADER = "X-CSRF-Token"
    CSRF_COOKIE = "csrf_token"

    # Public endpoints that don't need CSRF (no existing session)
    EXCLUDED_PREFIXES = [
        "/api/tenants/login",
        "/api/tenants/register",
        "/api/tenants/forgot-password",
        "/api/tenants/reset-password",
        "/api/auth/login",
    ]

    async def dispatch(self, request: Request, call_next):
        # Skip safe methods
        if request.method not in self.SAFE_METHODS:
            # Check if path is excluded
            path = request.url.path
            is_excluded = any(
                path.startswith(prefix) for prefix in self.EXCLUDED_PREFIXES
            )

            if not is_excluded:
                token_header = request.headers.get(self.CSRF_HEADER)
                token_cookie = request.cookies.get(self.CSRF_COOKIE)

                if not token_header or not token_cookie or token_header != token_cookie:
                    if settings.CSRF_ENABLED:
                        logger.warning(
                            "CSRF validation failed: %s %s", request.method, path
                        )
                        return JSONResponse(
                            status_code=HTTP_403_FORBIDDEN,
                            content={"detail": "CSRF token inválido"},
                        )
                    else:
                        logger.debug(
                            "CSRF warn mode: missing/invalid token for %s %s",
                            request.method,
                            path,
                        )

        response = await call_next(request)

        # Ensure CSRF cookie is set on every response (for double-submit pattern)
        if not request.cookies.get(self.CSRF_COOKIE):
            token = secrets.token_hex(32)
            response.set_cookie(
                key=self.CSRF_COOKIE,
                value=token,
                httponly=False,  # Must be readable by JS
                samesite="lax",
                secure=settings.COOKIE_SECURE,  # Uses COOKIE_SECURE from settings
                max_age=86400,  # 24 hours
            )

        return response
