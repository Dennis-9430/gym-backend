"""Helper para manejar JWT en cookies HttpOnly + fallback a Authorization header.

Con el proxy de Vercel (same-origin), usamos SameSite=Lax.
No se necesita Partitioned ni SameSite=None."""

from typing import Optional
from datetime import timedelta

from fastapi import Request, Response
from app.config import settings


def set_auth_cookie(response: Response, token: str, expires_delta: Optional[timedelta] = None):
    """Setea el JWT como cookie HttpOnly, Secure, SameSite=Lax.

    Con el proxy de Vercel, las requests son same-origin,
    por lo que SameSite=Lax es suficiente y más seguro.
    """
    max_age = int(expires_delta.total_seconds()) if expires_delta else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    response.set_cookie(
        key="access_token",
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN or None,
        path="/",
    )


def clear_auth_cookie(response: Response):
    """Elimina la cookie de autenticación (para logout)."""
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN or None,
        path="/",
    )


def get_token_from_request(request: Request) -> Optional[str]:
    """Extrae el JWT de la cookie HttpOnly o del header Authorization.
    
    Orden de precedencia:
    1. Cookie access_token (HttpOnly)
    2. Header Authorization: Bearer <token>
    
    Esto permite migración gradual: los clientes nuevos usan cookie,
    los existentes siguen usando el header.
    """
    # 1. Intentar desde cookie HttpOnly
    token = request.cookies.get("access_token")
    if token:
        return token
    
    # 2. Fallback a Authorization header (backward compat)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    return None
