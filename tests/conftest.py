"""Fixtures compartidos para tests de backend — multi-tenant auth"""

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.main import app
from app.database import get_database, Collections
from app.config import settings

# Usar base de datos de test separada
TEST_DB_NAME = f"{settings.MONGODB_DB_NAME}_test"


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop para pytest-asyncio."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def mongo_client() -> AsyncGenerator[AsyncIOMotorClient, None]:
    """Cliente MongoDB compartido para toda la sesión de test."""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    yield client
    # Limpiar base de datos de test al finalizar
    await client.drop_database(TEST_DB_NAME)
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_test_db(mongo_client: AsyncIOMotorClient):
    """Limpia todas las colecciones antes de cada test."""
    db = mongo_client[TEST_DB_NAME]
    collections = await db.list_collection_names()
    for col in collections:
        if not col.startswith("system."):
            await db[col].delete_many({})


@pytest_asyncio.fixture
async def test_db(mongo_client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    """Base de datos de test — apunta a gym_db_test."""
    return mongo_client[TEST_DB_NAME]


@pytest_asyncio.fixture
async def client(test_db: AsyncIOMotorDatabase) -> AsyncGenerator[AsyncClient, None]:
    """
    Cliente HTTP de prueba — sobreescribe get_database() para apuntar a la DB de test.
    No usa lifespan (no conecta MongoDB real, no ejecuta startup logic).
    """
    app.dependency_overrides = {}

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_database] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides = {}


# ─── Datos de prueba compartidos ─────────────────────────────────────────────
# Valores fijos para tests multi-tenant
TENANT_A = {
    "tenantId": "tenant-a-001",
    "businessCode": "gym-alpha",
    "businessName": "Gimnasio Alpha",
    "email": "alpha@demo.com",
    "password": "alpha123",
    "isDemo": True,
    "subscriptionStatus": "ACTIVE",
}
TENANT_B = {
    "tenantId": "tenant-b-002",
    "businessCode": "gym-beta",
    "businessName": "Gimnasio Beta",
    "email": "beta@demo.com",
    "password": "beta123",
    "isDemo": True,
    "subscriptionStatus": "ACTIVE",
}
TENANT_REAL = {
    "tenantId": "tenant-real-003",
    "businessCode": "real-gym",
    "businessName": "Gimnasio Real",
    "email": "real@gym.com",
    "isDemo": False,
    "subscriptionStatus": "ACTIVE",
}

EMPLOYEE_A = {
    "_id": "507f1f77bcf86cd799439011",
    "tenantId": "tenant-a-001",
    "username": "admin_alpha",
    "email": "admin@alpha.com",
    "firstName": "Admin",
    "lastName": "Alpha",
    "role": "ADMIN",
    "isOwner": True,
    "status": "ACTIVE",
}
EMPLOYEE_B = {
    "_id": "507f1f77bcf86cd799439012",
    "tenantId": "tenant-b-002",
    "username": "admin_beta",
    "email": "admin@beta.com",
    "firstName": "Admin",
    "lastName": "Beta",
    "role": "ADMIN",
    "isOwner": True,
    "status": "ACTIVE",
}
EMPLOYEE_REAL = {
    "_id": "507f1f77bcf86cd799439013",
    "tenantId": "tenant-real-003",
    "username": "admin_real",
    "email": "admin@real.com",
    "firstName": "Admin",
    "lastName": "Real",
    "role": "ADMIN",
    "isOwner": True,
    "status": "ACTIVE",
}

# Mismo username para probar colisión multi-tenant
USER_A = {
    "username": "admin_alpha",
    "tenantId": "tenant-a-001",
    "employeeId": "507f1f77bcf86cd799439011",
    "password_hash": "",  # Se setea en fixture
    "isOwner": True,
}
USER_B = {
    "username": "admin_beta",
    "tenantId": "tenant-b-002",
    "employeeId": "507f1f77bcf86cd799439012",
    "password_hash": "",
    "isOwner": True,
}
USER_REAL = {
    "username": "admin_real",
    "tenantId": "tenant-real-003",
    "employeeId": "507f1f77bcf86cd799439013",
    "password_hash": "",
    "isOwner": True,
}

# Mismo username en dos tenants para probar ambigüedad
USER_COLLISION_A = {
    "username": "admin_collision",
    "tenantId": "tenant-a-001",
    "employeeId": "507f1f77bcf86cd799439011",
    "password_hash": "",
    "isOwner": True,
}
USER_COLLISION_B = {
    "username": "admin_collision",
    "tenantId": "tenant-b-002",
    "employeeId": "507f1f77bcf86cd799439012",
    "password_hash": "",
    "isOwner": True,
}


@pytest_asyncio.fixture
async def seed_data(test_db: AsyncIOMotorDatabase):
    """Puebla datos de prueba multi-tenant con contraseñas hasheadas."""
    from app.auth.utils import get_password_hash

    # Hashear contraseñas
    for user in [USER_A, USER_B, USER_REAL, USER_COLLISION_A, USER_COLLISION_B]:
        user["password_hash"] = get_password_hash("password123")

    # Insertar tenants
    await test_db[Collections.TENANTS].insert_many([TENANT_A, TENANT_B, TENANT_REAL])

    # Insertar employees
    await test_db[Collections.EMPLOYEES].insert_many([
        EMPLOYEE_A, EMPLOYEE_B, EMPLOYEE_REAL,
    ])

    # Insertar users
    await test_db[Collections.USERS].insert_many([
        USER_A, USER_B, USER_REAL, USER_COLLISION_A, USER_COLLISION_B,
    ])

    return {
        "tenants": [TENANT_A, TENANT_B, TENANT_REAL],
        "employees": [EMPLOYEE_A, EMPLOYEE_B, EMPLOYEE_REAL],
        "users": [USER_A, USER_B, USER_REAL, USER_COLLISION_A, USER_COLLISION_B],
    }
