"""Servicio de gestión de tokens de recuperación de contraseña (one-time)."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import Collections


def _now_utc() -> datetime:
    """Retorna datetime UTC sin timezone (naive), compatible con MongoDB existente."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(token: str) -> str:
    """Hash SHA-256 del token para almacenamiento seguro en DB."""
    return hashlib.sha256(token.encode()).hexdigest()


async def create_reset_token(
    db: AsyncIOMotorDatabase,
    username: str,
    tenant_id: str,
    employee_id: str,
    expires_in_minutes: int = 15,
) -> str:
    """Crea un token de recuperación one-time y lo guarda en DB.
    
    Returns:
        El token en texto plano (para incluir en el link del email).
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    expires_at = _now_utc() + timedelta(minutes=expires_in_minutes)

    await db[Collections.PASSWORD_RESET_TOKENS].insert_one({
        "token_hash": token_hash,
        "username": username,
        "tenantId": tenant_id,
        "employeeId": employee_id,
        "expiresAt": expires_at,
        "used": False,
        "usedAt": None,
        "createdAt": _now_utc(),
    })

    return raw_token


async def consume_reset_token(
    db: AsyncIOMotorDatabase,
    raw_token: str,
) -> Optional[dict]:
    """Consume (marca como usado) un token de recuperación.
    
    Returns:
        Dict con username, tenantId, employeeId si el token es válido y no fue usado.
        None si el token es inválido, expiró o ya fue usado.
    """
    token_hash = _hash_token(raw_token)

    # Buscar token
    doc = await db[Collections.PASSWORD_RESET_TOKENS].find_one({
        "token_hash": token_hash,
    })

    if not doc:
        return None

    # Verificar expiración
    expires_at = doc.get("expiresAt")
    if expires_at and expires_at < _now_utc():
        await db[Collections.PASSWORD_RESET_TOKENS].delete_one({"_id": doc["_id"]})
        return None

    # Verificar si ya fue usado
    if doc.get("used", False):
        return None

    # Marcar como usado (one-time)
    await db[Collections.PASSWORD_RESET_TOKENS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"used": True, "usedAt": _now_utc()}},
    )

    return {
        "username": doc["username"],
        "tenantId": doc["tenantId"],
        "employeeId": doc["employeeId"],
    }


async def invalidate_user_tokens(db: AsyncIOMotorDatabase, username: str, tenant_id: str):
    """Invalida todos los tokens activos de un usuario (ej: después de cambio manual de password)."""
    await db[Collections.PASSWORD_RESET_TOKENS].update_many(
        {
            "username": username,
            "tenantId": tenant_id,
            "used": False,
        },
        {"$set": {"used": True, "usedAt": _now_utc()}},
    )
