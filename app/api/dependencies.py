"""Shared authentication/authorization dependencies for FastAPI routes.

Centralizes auth deps that were previously scattered across routers:
- get_current_user: re-exported from auth/router.py
- get_current_tenant: resolves full tenant document from JWT
- require_roles: role-based access control factory
- require_plan: plan-based access control factory
- resolve_tenant: utility to lookup tenant by tenantId or businessCode
- get_current_tenant_id: lightweight tenantId extraction without DB call
"""

from typing import Optional, List, Callable
from fastapi import Depends, HTTPException, status, Request

from app.auth.router import get_current_user
from app.auth.schemas import UserResponse, UserRole
from app.database import get_database, Collections
from app.models.tenant import SubscriptionPlan


async def get_current_tenant(
    current_user: UserResponse = Depends(get_current_user),
) -> dict:
    """Resolve the current tenant from the authenticated user's tenantId.

    Fetches the full tenant document from the database.
    Raises 400 if user has no tenantId, 404 if tenant not found.
    """
    tenant_id = current_user.tenantId
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sin tenant asociado",
        )

    db = get_database()
    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado",
        )
    return tenant


async def get_current_tenant_id(
    current_user: UserResponse = Depends(get_current_user),
) -> str:
    """Lightweight extraction of tenantId from JWT claims — no DB call.

    Raises 400 if user has no tenantId.
    """
    if not current_user.tenantId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sin tenant asociado",
        )
    return current_user.tenantId


def require_roles(*roles: UserRole) -> Callable:
    """Dependency factory: require the authenticated user to have one of the specified roles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(current_user: UserResponse = Depends(require_roles(UserRole.ADMIN))):
            ...
    """
    async def role_checker(current_user: UserResponse = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenés permisos para acceder a este recurso",
            )
        return current_user
    return role_checker


def require_plan(*plans: SubscriptionPlan) -> Callable:
    """Dependency factory: require the tenant to have one of the specified subscription plans.

    Usage:
        @router.get("/premium-feature")
        async def premium_endpoint(current_user: UserResponse = Depends(require_plan(SubscriptionPlan.PREMIUM))):
            ...
    """
    allowed_plans = {p.value for p in plans}

    async def plan_checker(current_user: UserResponse = Depends(get_current_user)):
        if current_user.plan not in allowed_plans:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu plan no incluye esta funcionalidad",
            )
        return current_user
    return plan_checker


async def resolve_tenant(identifier: str) -> Optional[dict]:
    """Resolve a tenant by tenantId or businessCode.

    Useful for SUPER_ADMIN routes that need to look up tenants by identifier.
    Returns None if no tenant matches.
    """
    db = get_database()
    tenant = await db[Collections.TENANTS].find_one({"tenantId": identifier})
    if tenant:
        return tenant
    tenant = await db[Collections.TENANTS].find_one({"businessCode": identifier})
    return tenant
