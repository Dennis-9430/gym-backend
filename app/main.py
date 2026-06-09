# Punto de entrada de la aplicación FastAPI
# Relacionado con: config.py, database.py
"""FastAPI application entry point"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send, Message
from app.config import settings
from app.database import connect_to_mongodb, close_mongodb_connection
from app.models.error import APIError, APIErrorDetail, ErrorCodes
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("uvicorn")

# ── Status code to error code mapping (Option C) ────────────────────────
STATUS_CODE_MAP = {
    400: ErrorCodes.VALIDATION_ERROR,
    401: ErrorCodes.UNAUTHORIZED,
    403: ErrorCodes.FORBIDDEN,
    404: ErrorCodes.NOT_FOUND,
    409: ErrorCodes.CONFLICT,
    422: ErrorCodes.VALIDATION_ERROR,
    429: ErrorCodes.RATE_LIMITED,
    500: ErrorCodes.INTERNAL_ERROR,
}


class CatchAllErrorMiddleware:
    """ASGI middleware que captura excepciones no manejadas y retorna JSON genérico.

    A diferencia de @app.exception_handler(Exception), este middleware es
    puramente ASGI (no BaseHTTPMiddleware) y se ubica al final de la cadena
    de middlewares, atrapando excepciones que escapan incluso de
    BaseHTTPMiddleware (RateLimitMiddleware, PlanProtectionMiddleware).

    Si los headers ya fueron enviados (response_started=True), solo loguea
    y suprime la excepción — el handler interno ya envió la respuesta.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            logger.error(
                "Unhandled error on %s: %s", scope.get("path", ""), exc, exc_info=True
            )
            if not response_started:
                response = JSONResponse(
                    status_code=500,
                    content=APIError(
                        error=APIErrorDetail(
                            code=ErrorCodes.INTERNAL_ERROR,
                            detail="Error interno del servidor",
                            message="Error interno del servidor",
                        )
                    ).model_dump(),
                )
                await response(scope, receive, send)
from app.auth.router import router as auth_router
from app.routers.employees import router as employees_router
from app.routers.clients import router as clients_router
from app.routers.services import router as services_router
from app.routers.products import router as products_router
from app.routers.sales import router as sales_router
from app.routers.attendance import router as attendance_router
from app.routers.reports import router as reports_router
from app.routers.tenants import router as tenants_router
from app.routers.notifications import router as notifications_router
from app.routers.invoices import router as invoices_router
from app.routers.demo import router as demo_router
from app.routers.admin import router as admin_router
from app.routers.fingerprints import router as fingerprints_router
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.csrf import CSRFTokenMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.plan_protection import PlanProtectionMiddleware
from app.middleware.cors import CORSMiddleware as _CORSHandler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa MongoDB al iniciar la app
    # Relacionado con: database.py, auth/service.py
    """Application lifespan events — fail-fast en producción"""
    import logging
    logger = logging.getLogger("uvicorn")
    
    # Startup: conexión MongoDB es CRÍTICA — fallar rápido
    await connect_to_mongodb()
    logger.info("MongoDB conectado")
    
    # Validación de índices críticos (solo lectura — no crea ni dropea).
    from app.database import validate_required_indexes
    missing_indexes = await validate_required_indexes()
    if missing_indexes:
        logger.warning(
            "Índices críticos faltantes (%d). Ejecutá: python scripts/migrate_indexes.py\n  - %s",
            len(missing_indexes),
            "\n  - ".join(missing_indexes),
        )
    else:
        logger.info("Índices críticos verificados")
    
    # Inicializar usuarios por defecto (admin/receptor) — gated por flag
    if settings.ENABLE_DEFAULT_USERS:
        from app.auth.service import initialize_default_users
        await initialize_default_users()
        logger.info("Usuarios default inicializados")
    else:
        logger.info("Usuarios default desactivados (ENABLE_DEFAULT_USERS=false)")
    
    # Crear SUPER_ADMIN si las credenciales están configuradas
    from app.database import create_super_admin
    await create_super_admin()
    logger.info("SUPER_ADMIN verificado")
    
    # Inicializar empleados seed (demo data) — gated por ENABLE_DEMO_SEED
    if settings.ENABLE_DEMO_SEED:
        from app.routers.employees import initialize_seed_employees
        await initialize_seed_employees()
        logger.info("Empleados seed inicializados")
    else:
        logger.info("Empleados seed desactivados (ENABLE_DEMO_SEED=false)")
    
    # Inicializar tenant demo si no existe — gated por ENABLE_DEMO_SEED
    if settings.ENABLE_DEMO_SEED:
        from app.services.tenant_demo import initialize_tenant_demo
        await initialize_tenant_demo()
        logger.info("Tenant demo inicializado")
    
    # Iniciar scheduler de notificaciones — gated por flag
    if settings.ENABLE_SCHEDULER:
        from app.scheduler.jobs import start_scheduler
        start_scheduler()
        logger.info("Scheduler iniciado")
    else:
        logger.info("Scheduler desactivado (ENABLE_SCHEDULER=false)")
    
    yield
    # Shutdown
    await close_mongodb_connection()


# Swagger docs/redoc/openapi solo en desarrollo (DEBUG=True)
# En producción, se deshabilitan para reducir superficie de ataque
if settings.DEBUG:
    app = FastAPI(
        title="Gym Management API",
        description="Backend API for Gym Management System",
        version="1.0.0",
        lifespan=lifespan,
    )
else:
    app = FastAPI(
        title="Gym Management API",
        description="Backend API for Gym Management System",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

# ── Custom exception handlers ──────────────────────────────────────────
# Estandarizan todas las respuestas error al formato {error: {code, detail, message}}.
# Se registran ANTES de los middlewares para interceptar HTTPException a nivel app.

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    detail = exc.detail
    code = STATUS_CODE_MAP.get(exc.status_code, ErrorCodes.INTERNAL_ERROR)
    message = detail if isinstance(detail, str) else str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=APIError(
            error=APIErrorDetail(code=code, detail=message, message=message)
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content=APIError(
            error=APIErrorDetail(
                code=ErrorCodes.VALIDATION_ERROR,
                detail=str(exc),
                message="Error de validación"
            )
        ).model_dump(),
    )


# CORS middleware custom — refleja el Origin para permitir allow_credentials=True
# con cualquier origen. No usa Starlette CORSMiddleware porque no permite
# allow_origins=["*"] + allow_credentials=True (lo prohibe el spec de CORS).
# Ver app/middleware/cors.py para los detalles.
app.add_middleware(_CORSHandler)


@app.get("/")
async def root():
    # Endpoint raíz que retorna información de la API
    """Root endpoint"""
    return {
        "message": "Gym Management API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    # Verifica que la API esté funcionando
    """Health check endpoint"""
    return {"status": "healthy"}


# Incluir todas las rutas del API
# Relacionado con: auth/router.py, routers/*
app.include_router(auth_router)
app.include_router(employees_router)
app.include_router(clients_router)
app.include_router(services_router)
app.include_router(products_router)
app.include_router(sales_router)
app.include_router(attendance_router)
app.include_router(reports_router)
app.include_router(tenants_router)
app.include_router(notifications_router)
app.include_router(invoices_router)
app.include_router(demo_router)
app.include_router(admin_router)
app.include_router(fingerprints_router)

# Rate limiting - 1000 requests por minuto (suficiente para bursts del dashboard SPA)
app.add_middleware(RateLimitMiddleware, rate_limit=1000)

# CSRF protection - Double Submit Cookie (warn-only mode by default)
# SEGURIDAD: En warn mode, solo loguea advertencias sin bloquear.
# Setear CSRFT_ENABLED=True en producción SOLO después de que el frontend
# envíe X-CSRF-Token header en todas las mutaciones.
app.add_middleware(CSRFTokenMiddleware)

# Security headers — OWASP-recommended HTTP response headers
# SEGURIDAD: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection,
# Strict-Transport-Security, Referrer-Policy en cada respuesta.
app.add_middleware(SecurityHeadersMiddleware)

# Plan protection middleware - protege rutas PREMIUM (/api/employees, /api/reports)
# SEGURIDAD: No afecta uso local (todos los tenants demo tienen subscription ACTIVE)
app.add_middleware(PlanProtectionMiddleware)

# ── Catch-all error middleware (ASGI puro, NO BaseHTTPMiddleware) ──────────
# SEGURIDAD: Atrapa TODAS las excepciones no manejadas, incluso las que
# escapan de BaseHTTPMiddleware (RateLimitMiddleware, PlanProtectionMiddleware).
# Es el middleware más externo — agregarlo último = ejecutarse primero.
# HTTPException sigue manejándose por el built-in handler de Starlette.
app.add_middleware(CatchAllErrorMiddleware)


if __name__ == "__main__":
    # Inicia el servidor uvicorn
    # Relacionado con: config.py
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Escuchar en todas las interfaces
        port=8000,
        reload=settings.DEBUG
    )