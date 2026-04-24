# Utilidades para verificación de plan y suscripciones
# Relacionado con: routers/*, middleware/*
"""Plan and subscription verification utilities"""
from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse
from app.database import get_database
from app.models.tenant import SubscriptionStatus


# Definición de características por plan
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
    """Obtiene las características permitidas para un plan"""
    return PLAN_FEATURES.get(plan, [])


def has_feature(plan: str, feature: str) -> bool:
    """Verifica si un plan tiene una característica específica"""
    features = get_plan_features(plan)
    return feature in features


def check_subscription_active(tenant_id: str) -> dict:
    """Verifica si la suscripción del tenant está activa"""
    db = get_database()
    tenant = db.tenants.find_one({"tenantId": tenant_id})
    
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
    
    return {
        "active": True,
        "plan": tenant.get("plan", "BASIC")
    }


def require_plan_feature(feature: str):
    """Decorator para requerir una característica de plan"""
    def dependency(request: Request):
        # Extraer tenantId del token o header
        tenant_id = None
        
        # Del token Authorization
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            from app.auth.utils import decode_token
            token = auth_header.replace("Bearer ", "")
            payload = decode_token(token)
            if payload:
                tenant_id = payload.get("tenantId")
        
        # Del header X-Tenant-ID
        if not tenant_id:
            tenant_id = request.headers.get("X-Tenant-ID")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant no identificado"
            )
        
        # Verificar suscripción activa
        sub_info = check_subscription_active(tenant_id)
        plan = sub_info["plan"]
        
        # Verificar característica
        if not has_feature(plan, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta funcionalidade requiere el plan PREMIUM. Tu plan actual: {plan}"
            )
        
        return {"tenantId": tenant_id, "plan": plan}
    
    return dependency


def require_premium():
    """Decorator para requerir plan PREMIUM"""
    return require_plan_feature("employees:write")


def get_tenant_plan(tenant_id: str) -> str:
    """Obtiene el plan de un tenant"""
    db = get_database()
    tenant = db.tenants.find_one({"tenantId": tenant_id})
    
    if not tenant:
        return "BASIC"
    
    return tenant.get("plan", "BASIC")


def get_tenant_subscription_status(tenant_id: str) -> str:
    """Obtiene el estado de suscripción de un tenant"""
    db = get_database()
    tenant = db.tenants.find_one({"tenantId": tenant_id})
    
    if not tenant:
        return "PENDING"
    
    return tenant.get("subscriptionStatus", "PENDING")


def can_access_feature(tenant_id: str, feature: str) -> bool:
    """Verifica si un tenant puede acceder a una característica"""
    try:
        sub_info = check_subscription_active(tenant_id)
        if not sub_info["active"]:
            return False
        return has_feature(sub_info["plan"], feature)
    except HTTPException:
        return False