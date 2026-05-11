# Punto de entrada de la aplicación FastAPI
# Relacionado con: config.py, database.py
"""FastAPI application entry point"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import connect_to_mongodb, close_mongodb_connection
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
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.plan_protection import PlanProtectionMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa MongoDB al iniciar la app
    # Relacionado con: database.py, auth/service.py
    """Application lifespan events"""
    try:
        # Startup
        await connect_to_mongodb()
        print("[OK] MongoDB conectado")
        
        # Crear índices de base de datos
        from app.database import create_indexes
        await create_indexes()
        print("[OK] Indices creados")
        
        # Inicializar usuarios por defecto
        from app.auth.service import initialize_default_users
        await initialize_default_users()
        print("[OK] Usuarios default inicializados")
        
        # Inicializar empleados seed si no existen
        from app.routers.employees import initialize_seed_employees
        await initialize_seed_employees()
        print("[OK] Empleados seed inicializados")
        
        # Inicializar tenant demo si no existe
        from app.routers.tenants import initialize_tenant_demo
        await initialize_tenant_demo()
        print("[OK] Tenant demo inicializado")
        
        # Iniciar scheduler de notificaciones
        from app.scheduler.jobs import start_scheduler
        start_scheduler()
        print("[OK] Scheduler iniciado")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
    
    yield
    # Shutdown
    await close_mongodb_connection()


app = FastAPI(
    title="Gym Management API",
    description="Backend API for Gym Management System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware - orígenes configurables por ALLOWED_ORIGINS
# SEGURIDAD: En producción, definir ALLOWED_ORIGINS con dominios específicos
# Ej: ALLOWED_ORIGINS=https://app.gymtuempresa.com,https://gymtuempresa.com
allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
if allowed_origins == ["*"]:
    # Modo local: permitir todos (allow_credentials=False cuando es *)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Modo producción: orígenes específicos
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


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

# Rate limiting - 1000 requests por minuto (suficiente para bursts del dashboard SPA)
app.add_middleware(RateLimitMiddleware, rate_limit=1000)

# Plan protection middleware - protege rutas PREMIUM (/api/employees, /api/reports)
# SEGURIDAD: No afecta uso local (todos los tenants demo tienen subscription ACTIVE)
app.add_middleware(PlanProtectionMiddleware)



if __name__ == "__main__":
    # Inicia el servidor uvicorn
    # Relacionado con: config.py
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Escuchar en todas las interfaces
        port=8000,
        reload=True
    )