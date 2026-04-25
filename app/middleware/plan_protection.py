# Middleware de protección por plan
# Relacionado con: routers/*, utils/plans.py
"""Plan-based access control middleware"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.plans import check_subscription_active, has_feature, PLAN_FEATURES
import logging

logger = logging.getLogger(__name__)


class PlanProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware para proteger rutas según el plan del tenant"""
    
    # Rutas que son PREMIUM ONLY (todas las operaciones)
    PREMIUM_ROUTES = [
        "/api/employees",
        "/api/reports",
        "/api/tenants",
    ]
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        
        # Solo proteger rutas de API
        if not path.startswith("/api/"):
            return await call_next(request)
        
        # Rutas que NO requieren protección - permitir todo
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
        
        # Obtener tenant ID
        tenant_id = self._get_tenant_id(request)
        
        # Rutas públicas - permitir sin verificar
        public_routes = ["/register", "/login", "/docs", "/openapi", "/health"]
        for route in public_routes:
            if path.startswith(f"/api{route}") or path == route:
                return await call_next(request)
        
        # Si no hay tenant, dejar pasar para /register, /login
        if not tenant_id:
            logger.info(f"[PLAN] No tenant_id, allowing: {path}")
            return await call_next(request)
        
        logger.info(f"[PLAN] Checking access for tenant: {tenant_id}, path: {path}")
        
        # Verificar suscripción activa y obtener plan
        try:
            sub_info = check_subscription_active(tenant_id)
            plan = sub_info.get("plan", "BASIC")
            logger.info(f"[PLAN] Tenant {tenant_id} has plan: {plan}")
        except HTTPException as e:
            logger.info(f"[PLAN] Subscription error: {e.detail}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        
        # Verificar si la ruta requiere PREMIUM
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
    
def _get_tenant_id(self, request: Request) -> str:
        """Extrae el tenant ID de la request"""
        # Del header X-Tenant-ID
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            return tenant_id
        
        # Del header Authorization (Bearer token)
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