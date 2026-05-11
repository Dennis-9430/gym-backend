# Utilidades para verificación de plan y suscripciones
# Relacionado con: routers/*, middleware/*
"""Plan and subscription verification utilities"""
from fastapi import HTTPException, status, Request
from app.database import get_database
from app.models.tenant import SubscriptionStatus


PLAN_FEATURES = {
    "BASIC": [
        "clients:read",
        "clients:write",
        "memberships:read",
        "memberships:write",
        "products:read",
        "products:write",
        "sales:read",
        "sales:write",
        "attendance:read",
        "attendance:write",
    ],
    "PREMIUM": [
        "clients:read",
        "clients:write",
        "memberships:read",
        "memberships:write",
        "products:read",
        "products:write",
        "sales:read",
        "sales:write",
        "attendance:read",
        "attendance:write",
        "employees:read",
        "employees:write",
        "reports:read",
        "reports:write",
        "config:read",
        "config:write",
    ]
}


def get_plan_features(plan: str) -> list:
    return PLAN_FEATURES.get(plan, [])


def has_feature(plan: str, feature: str) -> bool:
    return feature in get_plan_features(plan)


async def check_subscription_active(tenant_id: str) -> dict:
    db = get_database()
    tenant = await db.tenants.find_one({"tenantId": tenant_id})

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado"
        )

    sub_status = tenant.get("subscriptionStatus", "PENDING")
    if sub_status != SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Suscripción {sub_status}. Por favor renueva tu plan."
        )

    return {"active": True, "plan": tenant.get("plan", "BASIC")}


async def get_tenant_plan(tenant_id: str) -> str:
    db = get_database()
    tenant = await db.tenants.find_one({"tenantId": tenant_id})
    if not tenant:
        return "BASIC"
    return tenant.get("plan", "BASIC")


async def get_tenant_subscription_status(tenant_id: str) -> str:
    db = get_database()
    tenant = await db.tenants.find_one({"tenantId": tenant_id})
    if not tenant:
        return "PENDING"
    return tenant.get("subscriptionStatus", "PENDING")


async def can_access_feature(tenant_id: str, feature: str) -> bool:
    try:
        sub_info = await check_subscription_active(tenant_id)
        return sub_info["active"] and has_feature(sub_info["plan"], feature)
    except HTTPException:
        return False


def require_plan_feature(feature: str):
    async def dependency(request: Request):
        tenant_id = None

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            from app.auth.utils import decode_token
            token = auth_header.replace("Bearer ", "")
            payload = decode_token(token)
            if payload:
                tenant_id = payload.get("tenantId")

        if not tenant_id:
            tenant_id = request.headers.get("X-Tenant-ID")

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant no identificado"
            )

        sub_info = await check_subscription_active(tenant_id)
        plan = sub_info["plan"]

        if not has_feature(plan, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta funcionalidad requiere el plan PREMIUM. Tu plan actual: {plan}"
            )

        return {"tenantId": tenant_id, "plan": plan}

    return dependency


def require_premium():
    return require_plan_feature("employees:write")
