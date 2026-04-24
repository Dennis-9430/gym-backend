# Configuración de conexión a MongoDB usando Motor async driver
# Relacionado con: config.py, main.py
"""MongoDB database connection using Motor async driver"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from app.config import settings

_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongodb() -> None:
    # Inicializa la conexión a MongoDB
    # Relacionado con: main.py (lifespan)
    """Initialize MongoDB connection"""
    global _client, _database
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    _database = _client[settings.MONGODB_DB_NAME]
    
    # Verifica que la conexión funcione
    await _client.admin.command("ping")
    print(f"Connected to MongoDB: {settings.MONGODB_DB_NAME}")


async def close_mongodb_connection() -> None:
    # Cierra la conexión cuando la app se detiene
    # Relacionado con: main.py (lifespan)
    """Close MongoDB connection"""
    global _client
    if _client:
        _client.close()
        print("MongoDB connection closed")


def get_database() -> AsyncIOMotorDatabase:
    # Retorna la instancia de la base de datos
    # Relacionado con: routers/*
    """Get database instance"""
    if _database is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongodb first.")
    return _database


# Funciones helper para obtener colecciones
async def get_collection(name: str):
    # Obtiene una colección por nombre
    # Relacionado con: routers/*
    """Get a collection by name"""
    db = get_database()
    return db[name]


# Constantes con los nombres de las colecciones
# Relacionado con: models/*
class Collections:
    TENANTS = "tenants"
    USERS = "users"
    EMPLOYEES = "employees"
    CLIENTS = "clients"
    PRODUCTS = "products"
    SALES = "sales"
    ATTENDANCE = "attendance"
    SERVICES = "services"