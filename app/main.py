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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa MongoDB al iniciar la app
    # Relacionado con: database.py, auth/service.py
    """Application lifespan events"""
    # Startup
    await connect_to_mongodb()
    from app.auth.service import initialize_default_users
    await initialize_default_users()
    yield
    # Shutdown
    await close_mongodb_connection()


app = FastAPI(
    title="Gym Management API",
    description="Backend API for Gym Management System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware permite conexiones desde el frontend
# Relacionado con: frontend (React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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



if __name__ == "__main__":
    # Inicia el servidor uvicorn
    # Relacionado con: config.py
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )