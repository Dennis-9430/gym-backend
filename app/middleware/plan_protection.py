# Middleware de protección por plan
# Relacionado con: routers/*, utils/plans.py
"""Plan-based access control middleware"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.auth.cookie import get_token_from_request
from app.utils.plans import PLAN_FEATURES
import logging

logger = logging.getLogger(__name__)


class PlanProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware para proteger rutas PREMIUM según el plan del tenant.
    
    - Rutas públicas de auth/registro: siempre permitidas.
    - Rutas BASIC: siempre permitidas (controladas por auth en cada endpoint).
    - Rutas PREMIUM (/api/employees, /api/reports): bloqueadas si plan != PREMIUM.
    - Si no se puede extraer tenantId (no autenticado): permitir (el endpoint rechazará).
    """
    
    # Rutas que NO requieren verificación de plan
    PUBLIC_PREFIXES = [
        "/api/auth/",
        "/api/tenants/register",
        "/api/tenants/login",
        "/api/tenants/plans",
        "/api/demo/",
    ]
    
    # Rutas que requieren plan PREMIUM
    PREMIUM_PREFIXES = [
        "/api/employees",
        "/api/reports",
    ]
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Solo aplicar a /api/*
        if not path.startswith("/api/"):
            return await call_next(request)
        
        # Siempre permitir rutas públicas (auth, registro, etc.)
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)
        
        # Extraer tenantId del JWT (fuente única)
        tenant_id = self._get_tenant_id_from_token(request)
        
        # Sin tenantId → usuario no autenticado, permitir (el endpoint hará auth)
        if not tenant_id:
            return await call_next(request)
        
        # Verificar suscripción activa
        try:
            sub_info = await self._check_subscription(tenant_id)
            plan = sub_info.get("plan", "BASIC")
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        
        # Verificar si la ruta requiere PREMIUM
        for prefix in self.PREMIUM_PREFIXES:
            if path.startswith(prefix) and plan != "PREMIUM":
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": f"Esta funcionalidad requiere el plan PREMIUM. Tu plan actual: {plan}"
                    }
                )
        
        return await call_next(request)
    
    def _get_tenant_id_from_token(self, request: Request) -> str | None:
        """Extrae tenantId del JWT desde cookie HttpOnly o Authorization header."""
        token = get_token_from_request(request)
        if not token:
            return None
        
        from jose import jwt, JWTError
        from app.config import settings
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            return payload.get("tenantId")
        except JWTError:
            return None
    
    async def _check_subscription(self, tenant_id: str) -> dict:
        """Verifica suscripción activa del tenant"""
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
        
        return {"active": True, "plan": tenant.get("plan", "BASIC")}