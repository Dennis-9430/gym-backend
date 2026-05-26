"""Helper para manejar JWT en cookies HttpOnly + fallback a Authorization header.

Usa Set-Cookie manual (no Starlette set_cookie) para poder agregar el
atributo Partitioned (CHIPS), necesario en Chrome 148+ con bloqueo de
third-party cookies activo."""

from typing import Optional
from datetime import timedelta
from urllib.parse import quote

from fastapi import Request, Response
from app.config import settings


def _cookie_header(key: str, value: str, max_age: int) -> str:
    """Construye el header Set-Cookie con Partitioned (CHIPS)."""
    parts = [f"{key}={quote(value, safe='')}"]
    parts.append(f"Max-Age={max_age}")
    parts.append("Path=/")
    if settings.COOKIE_DOMAIN:
        parts.append(f"Domain={settings.COOKIE_DOMAIN}")
    if settings.COOKIE_SECURE:
        parts.append("Secure")
    if settings.COOKIE_SAMESITE == "none":
        parts.append("SameSite=None")
    else:
        parts.append(f"SameSite={settings.COOKIE_SAMESITE}")
    parts.append("HttpOnly")
    parts.append("Partitioned")
    return "; ".join(parts)


def set_auth_cookie(response: Response, token: str, expires_delta: Optional[timedelta] = None):
    """Setea el JWT como cookie HttpOnly, Secure, SameSite, Partitioned.

    Partitioned (CHIPS) permite que Chrome envíe la cookie cross-site
    aunque el bloqueo de third-party cookies esté activo.
    """
    max_age = int(expires_delta.total_seconds()) if expires_delta else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.headers["set-cookie"] = _cookie_header("access_token", token, max_age)


def clear_auth_cookie(response: Response):
    """Elimina la cookie de autenticación (para logout)."""
    # Max-Age=0 o expires en pasado elimina la cookie
    response.headers["set-cookie"] = _cookie_header("access_token", "", max_age=0)


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
