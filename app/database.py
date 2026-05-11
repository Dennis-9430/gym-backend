# Configuración de conexión a MongoDB usando Motor async driver
# Relacionado con: config.py, main.py
"""MongoDB database connection using Motor async driver"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)

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


async def close_mongodb_connection() -> None:
    # Cierra la conexión cuando la app se detiene
    # Relacionado con: main.py (lifespan)
    """Close MongoDB connection"""
    global _client
    if _client:
        _client.close()


def get_database() -> AsyncIOMotorDatabase:
    # Retorna la instancia de la base de datos
    # Relacionado con: routers/*
    """Get database instance"""
    if _database is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongodb first.")
    return _database


async def get_collection(name: str):
    # Obtiene una colección por nombre
    # Relacionado con: routers/*
    """Get a collection by name"""
    db = get_database()
    return db[name]


class Collections:
    TENANTS = "tenants"
    USERS = "users"
    EMPLOYEES = "employees"
    CLIENTS = "clients"
    PRODUCTS = "products"
    SALES = "sales"
    ATTENDANCE = "attendance"
    SERVICES = "services"
    INVOICES = "invoices"
    COUNTERS = "counters"


async def create_indexes():
    """Crear índices idempotentes sin degradar unicidad silenciosamente."""
    db = get_database()

    index_configs = [
        (db[Collections.TENANTS], "tenantId", True),
        (db[Collections.TENANTS], "email", True),
        (db[Collections.USERS], "username", True),
        (db[Collections.EMPLOYEES], [("tenantId", 1), ("username", 1)], True),
        (db[Collections.CLIENTS], [("tenantId", 1), ("documentNumber", 1)], True),
        (db[Collections.PRODUCTS], [("tenantId", 1), ("code", 1)], True),
        (db[Collections.SERVICES], [("tenantId", 1), ("name", 1)], True),
        (db[Collections.USERS], [("tenantId", 1), ("employeeId", 1)], False),
        (db[Collections.INVOICES], [("tenantId", 1), ("invoiceNumber", 1)], True),
        (db[Collections.INVOICES], [("tenantId", 1), ("createdAt", -1)], False),
        (db[Collections.SALES], [("tenantId", 1), ("createdAt", -1)], False),
        (db[Collections.ATTENDANCE], [("tenantId", 1), ("clientId", 1), ("checkIn", -1)], False),
        (db[Collections.COUNTERS], [("tenantId", 1)], True),
        (db["notification_configs"], [("tenantId", 1), ("type", 1)], True),
        (db["notification_logs"], [("tenantId", 1), ("clientId", 1), ("sentAt", -1)], False),
    ]

    for collection, keys, unique in index_configs:
        try:
            await collection.create_index(keys, unique=unique, background=True)
        except Exception as e:
            if "duplicate" in str(e).lower() and unique:
                logger.warning(
                    "No se pudo crear índice único %s en %s por datos duplicados. Se mantiene el estado actual.",
                    keys,
                    collection.name,
                )
                continue
            logger.warning("No se pudo crear índice %s en %s: %s", keys, collection.name, e)
