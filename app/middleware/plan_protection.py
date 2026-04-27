# Middleware de protección por plan
# Relacionado con: routers/*, utils/plans.py
# IMPORTANTE: requiere async check_subscription_active
"""Plan-based access control middleware"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.plans import PLAN_FEATURES
import logging
import asyncio

logger = logging.getLogger(__name__)


async def check_subscription_active_async(tenant_id: str) -> dict:
    """Versión async de verificación de suscripción"""
    from app.database import get_database
    from app.models.tenant import SubscriptionStatus
    
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
    
    return {
        "active": True,
        "plan": tenant.get("plan", "BASIC")
    }


def has_feature(plan: str, feature: str) -> bool:
    """Verifica si un plan tiene una característica"""
    features = PLAN_FEATURES.get(plan, [])
    return feature in features


class PlanProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware para proteger rutas según el plan del tenant"""
    
    PREMIUM_ROUTES = [
        "/api/employees",
        "/api/reports",
        "/api/tenants",
    ]
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        
        if not path.startswith("/api/"):
            return await call_next(request)
        
        public_api_routes = [
            "/api/clients", 
            "/api/products", 
            "/api/sales", 
            "/api/services", 
            "/api/attendance", 
            "/api/auth",
            "/api/tenants",
        ]
        for route in public_api_routes:
            if path.startswith(route):
                return await call_next(request)
        
        tenant_id = await self._get_tenant_id(request)
        
        public_routes = ["/register", "/login", "/docs", "/openapi", "/health"]
        for route in public_routes:
            if path.startswith(f"/api{route}") or path == route:
                return await call_next(request)
        
        if not tenant_id:
            logger.info(f"[PLAN] No tenant_id, allowing: {path}")
            return await call_next(request)
        
        logger.info(f"[PLAN] Checking access for tenant: {tenant_id}, path: {path}")
        
        try:
            sub_info = await check_subscription_active_async(tenant_id)
            plan = sub_info.get("plan", "BASIC")
            logger.info(f"[PLAN] Tenant {tenant_id} has plan: {plan}")
        except HTTPException as e:
            logger.info(f"[PLAN] Subscription error: {e.detail}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        
        for route in self.PREMIUM_ROUTES:
            if path.startswith(route):
                logger.info(f"[PLAN] Route {route} requires PREMIUM, tenant has: {plan}")
                if plan != "PREMIUM":
                    logger.info(f"[PLAN] BLOCKING - returning 403")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": f"Esta funcionalidad requiere el plan PREMIUM. Tu plan actual: {plan}"
                        }
                    )
        
        return await call_next(request)
    
    async def _get_tenant_id(self, request: Request) -> str:
        """Extrae el tenant ID de la request"""
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            return tenant_id
        
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from jose import jwt, JWTError
            from app.config import settings
            
            token = auth_header.replace("Bearer ", "")
            try:
                payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
                tenant_id = payload.get("tenantId")
                if tenant_id:
                    return tenant_id
            except JWTError:
                pass
        
        return None