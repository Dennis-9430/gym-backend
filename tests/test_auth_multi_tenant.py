"""Tests multi-tenant auth: scoped login, unscoped rejection, demo compat, CRUD isolation.

NOTA sobre fixtures:
  El conftest.py tiene fixtures session-scoped que en Windows con
  pytest-asyncio mode=STRICT causan 'Event loop is closed' en teardown.
  Por eso este módulo define fixtures PROPIAS function-scoped que evitan ese
  conflicto y además inicializan app.database._database (necesario porque
  login_tenant() llama a get_database() directo, no via Depends).
"""

import pytest
import pytest_asyncio
from typing import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.main import app
from app.database import get_database, Collections
from app.config import settings
from app.auth.utils import get_password_hash
from app.middleware.rate_limit import set_store
from app.middleware.rate_limit_store import SlidingWindowMemoryStore


TEST_DB_NAME = f"{settings.MONGODB_DB_NAME}_test"


# ── Fixtures propios (function-scoped) ────────────────────────────────────────

@pytest_asyncio.fixture
async def mongo_client() -> AsyncGenerator[AsyncIOMotorClient, None]:
    """Cliente MongoDB — function-scoped, limpia DB al finalizar cada test."""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    yield client
    await client.drop_database(TEST_DB_NAME)
    client.close()


@pytest_asyncio.fixture
async def test_db(mongo_client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    """Base de datos de test (gym_db_test)."""
    return mongo_client[TEST_DB_NAME]


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Resetea rate limit store entre tests para evitar 429 falsos."""
    set_store(SlidingWindowMemoryStore())


@pytest_asyncio.fixture(autouse=True)
async def clean_test_db(mongo_client: AsyncIOMotorClient):
    """Limpia todas las colecciones antes de cada test."""
    db = mongo_client[TEST_DB_NAME]
    for col in await db.list_collection_names():
        if not col.startswith("system."):
            await db[col].delete_many({})


@pytest_asyncio.fixture
async def init_global_db(
    mongo_client: AsyncIOMotorClient,
    test_db: AsyncIOMotorDatabase,
):
    """Inicializa app.database._database para rutas que llaman get_database()
    directo, y sobreescribe dependency override para rutas que usan Depends."""
    import app.database as db_module
    db_module._client = mongo_client
    db_module._database = test_db

    app.dependency_overrides = {}

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_database] = override_get_db
    yield
    app.dependency_overrides = {}
    db_module._database = None
    db_module._client = None


@pytest_asyncio.fixture
async def client(
    test_db: AsyncIOMotorDatabase,
    init_global_db,
) -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTP contra la app FastAPI con DB de test."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Datos de prueba ──────────────────────────────────────────────────────────

TENANTS_RAW = [
    {
        "tenantId": "tenant-a-001",
        "businessCode": "gym-alpha",
        "businessName": "Gimnasio Alpha",
        "email": "alpha@demo.com",
        "password": "alpha123",
        "plan": "BASIC",
        "isDemo": True,
        "subscriptionStatus": "ACTIVE",
    },
    {
        "tenantId": "tenant-b-002",
        "businessCode": "gym-beta",
        "businessName": "Gimnasio Beta",
        "email": "beta@demo.com",
        "password": "beta123",
        "plan": "BASIC",
        "isDemo": True,
        "subscriptionStatus": "ACTIVE",
    },
    {
        "tenantId": "tenant-real-003",
        "businessCode": "real-gym",
        "businessName": "Gimnasio Real",
        "email": "real@gym.com",
        "plan": "BASIC",
        "isDemo": False,
        "subscriptionStatus": "ACTIVE",
    },
]

EMPLOYEES_RAW = [
    {
        "tenantId": "tenant-a-001",
        "username": "admin_alpha",
        "email": "admin@alpha.com",
        "firstName": "Admin",
        "lastName": "Alpha",
        "role": "ADMIN",
        "isOwner": True,
        "status": "ACTIVE",
    },
    {
        "tenantId": "tenant-b-002",
        "username": "admin_beta",
        "email": "admin@beta.com",
        "firstName": "Admin",
        "lastName": "Beta",
        "role": "ADMIN",
        "isOwner": True,
        "status": "ACTIVE",
    },
    {
        "tenantId": "tenant-real-003",
        "username": "admin_real",
        "email": "admin@real.com",
        "firstName": "Admin",
        "lastName": "Real",
        "role": "ADMIN",
        "isOwner": True,
        "status": "ACTIVE",
    },
]

USERS_RAW = [
    {"username": "admin_alpha",     "tenantId": "tenant-a-001", "isOwner": True},
    {"username": "admin_beta",      "tenantId": "tenant-b-002", "isOwner": True},
    {"username": "admin_real",      "tenantId": "tenant-real-003", "isOwner": True},
    {"username": "admin_collision", "tenantId": "tenant-a-001", "isOwner": True},
    {"username": "admin_collision", "tenantId": "tenant-b-002", "isOwner": True},
]


@pytest_asyncio.fixture
async def seed_data(test_db: AsyncIOMotorDatabase):
    """Puebla datos de prueba multi-tenant.

    - Inserta employees sin _id fijo para que MongoDB genere ObjectId.
    - Asigna esos ObjectId como employeeId en cada user (la ruta busca con
      ObjectId(employee_id), por eso deben coincidir).
    """
    from bson import ObjectId

    # 1. Insertar employees, capturar ids reales
    emp_ids = {}
    for emp in EMPLOYEES_RAW:
        result = await test_db[Collections.EMPLOYEES].insert_one(emp)
        emp_ids[emp["username"]] = str(result.inserted_id)

    # 2. Insertar users con employeeId correcto
    user_docs = []
    for u in USERS_RAW:
        username = u["username"]
        # Buscar el employee correspondiente (mismo tenant)
        emp_username = next(
            (e["username"] for e in EMPLOYEES_RAW
             if e["tenantId"] == u["tenantId"]),
            None,
        )
        user_docs.append({
            "username": username,
            "tenantId": u["tenantId"],
            "employeeId": emp_ids.get(emp_username, ""),
            "password_hash": get_password_hash("password123"),
            "isOwner": u["isOwner"],
        })

    await test_db[Collections.USERS].insert_many(user_docs)

    # 3. Insertar tenants
    await test_db[Collections.TENANTS].insert_many(TENANTS_RAW)


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Req 1: Login scopeado ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_scoped_works(client, seed_data):
    """Mismo username en dos tenants; login con businessCode autentica al correcto."""
    resp_a = await client.post("/api/tenants/login", json={
        "email": "admin_collision",
        "password": "password123",
        "businessCode": "gym-alpha",
    })
    assert resp_a.status_code == 200, (
        f"Login gym-alpha esperaba 200, obtuve {resp_a.status_code}: {resp_a.text}"
    )
    assert resp_a.json()["tenant"]["tenantId"] == "tenant-a-001"

    resp_b = await client.post("/api/tenants/login", json={
        "email": "admin_collision",
        "password": "password123",
        "businessCode": "gym-beta",
    })
    assert resp_b.status_code == 200, (
        f"Login gym-beta esperaba 200, obtuve {resp_b.status_code}: {resp_b.text}"
    )
    assert resp_b.json()["tenant"]["tenantId"] == "tenant-b-002"

    assert resp_a.json()["tenant"]["tenantId"] != resp_b.json()["tenant"]["tenantId"]


# ─── Req 2: Login sin scope rechazado para cuentas reales ─────────────────────

@pytest.mark.asyncio
async def test_login_without_scope_rejected_for_real(client, seed_data):
    """Tenant no-demo sin businessCode ni tenantId → 401."""
    resp = await client.post("/api/tenants/login", json={
        "email": "real@gym.com",
        "password": "password123",
    })
    assert resp.status_code == 401, (
        f"Esperaba 401, obtuve {resp.status_code}: {resp.text}"
    )


# ─── Req 3: Login sin scope permitido para demos ──────────────────────────────

@pytest.mark.asyncio
async def test_login_without_scope_allowed_for_demo(client, seed_data, test_db):
    """Demo sin businessCode ni tenantId puede loguearse (backward compat)."""
    # Hashear password como ocurre en producción (initialize_tenant_demo)
    await test_db[Collections.TENANTS].update_one(
        {"tenantId": "tenant-a-001"},
        {"$set": {"password": get_password_hash("alpha123")}},
    )

    resp = await client.post("/api/tenants/login", json={
        "email": "alpha@demo.com",
        "password": "alpha123",
    })
    assert resp.status_code == 200, (
        f"Login demo sin scope esperaba 200, obtuve {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    assert data["tenant"]["tenantId"] == "tenant-a-001"
    assert data["tenant"]["isDemo"] is True


# ─── Req 4: Forgot-password sin tenant responde genérico ──────────────────────

@pytest.mark.asyncio
async def test_forgot_password_without_scope_generic(client, seed_data):
    """Forgot-password sin businessCode ni tenantId → mensaje genérico."""
    resp = await client.post("/api/tenants/forgot-password", json={
        "email": "alpha@demo.com",
    })
    assert resp.status_code == 200
    generic_msg = resp.json()["message"]

    # Email inexistente → mismo mensaje (no revelar existencia)
    resp2 = await client.post("/api/tenants/forgot-password", json={
        "email": "noexiste@test.com",
    })
    assert resp2.status_code == 200
    assert resp2.json()["message"] == generic_msg

    # Scope correcto + email existente → sigue siendo genérico
    resp3 = await client.post("/api/tenants/forgot-password", json={
        "email": "admin_alpha",
        "businessCode": "gym-alpha",
    })
    assert resp3.status_code == 200
    assert resp3.json()["message"] == generic_msg


# ─── Req 5: /api/auth/login responde 410 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_legacy_auth_login_returns_410(client, seed_data):
    """POST /api/auth/login → HTTP 410 Gone."""
    resp = await client.post(
        "/api/auth/login",
        data={"username": "admin_collision", "password": "password123"},
    )
    assert resp.status_code == 410, (
        f"Esperaba 410, obtuve {resp.status_code}: {resp.text}"
    )
    detail = resp.json()["error"]["detail"].lower()
    assert "api/tenants/login" in detail or "deshabilitado" in detail


# ─── Req 6: Demo login con tenant.password legacy ─────────────────────────────

@pytest.mark.asyncio
async def test_demo_login_with_tenant_password_legacy(client, seed_data, test_db):
    """Demo sin user en 'users' puede loguearse con tenant.password (fallback)."""
    await test_db[Collections.TENANTS].update_one(
        {"tenantId": "tenant-a-001"},
        {"$set": {"password": get_password_hash("alpha123")}},
    )
    # email = tenant.email, NO es username de ningún user del tenant
    # → scoped path devuelve None, cae a tenant.password
    resp = await client.post("/api/tenants/login", json={
        "email": "alpha@demo.com",
        "password": "alpha123",
        "businessCode": "gym-alpha",
    })
    assert resp.status_code == 200, (
        f"Demo legacy login esperaba 200, obtuve {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    assert data["tenant"]["tenantId"] == "tenant-a-001"
    assert "accessToken" in data


# ─── Req 7: CRUD aislado por tenant ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_crud_isolated_by_tenant(client, seed_data, test_db):
    """Datos creados en tenant A NO son accesibles desde tenant B."""
    # ── 1. Login TENANT_REAL (no-demo) ──
    resp_real = await client.post("/api/tenants/login", json={
        "email": "admin_real",
        "password": "password123",
        "businessCode": "real-gym",
    })
    assert resp_real.status_code == 200, (
        f"Login REAL esperaba 200, obtuve {resp_real.status_code}: {resp_real.text}"
    )
    token_real = resp_real.json()["accessToken"]

    # ── 2. Crear cliente en TENANT_REAL ──
    resp_create = await client.post("/api/clients", json={
        "documentNumber": "1234567890",
        "firstName": "Carlos",
        "lastName": "Méndez",
        "documentType": "CEDULA",
    }, headers={"Authorization": f"Bearer {token_real}"})
    assert resp_create.status_code == 201, (
        f"Crear cliente esperaba 201, obtuve {resp_create.status_code}: {resp_create.text}"
    )
    client_id_real = resp_create.json()["id"]

    # ── 3. Login TENANT_A (demo, distinto tenant) ──
    resp_demo = await client.post("/api/tenants/login", json={
        "email": "admin_alpha",
        "password": "password123",
        "businessCode": "gym-alpha",
    })
    assert resp_demo.status_code == 200, (
        f"Login DEMO esperaba 200, obtuve {resp_demo.status_code}: {resp_demo.text}"
    )
    token_demo = resp_demo.json()["accessToken"]

    # ── 4. GET del cliente de REAL desde DEMO → 404 ──
    resp_get = await client.get(
        f"/api/clients/{client_id_real}",
        headers={"Authorization": f"Bearer {token_demo}"},
    )
    assert resp_get.status_code == 404, (
        f"Acceso cross-tenant esperaba 404, obtuve {resp_get.status_code}: {resp_get.text}"
    )

    # ── 5. Listar clientes desde DEMO → no incluye el de REAL ──
    resp_list = await client.get(
        "/api/clients",
        headers={"Authorization": f"Bearer {token_demo}"},
    )
    assert resp_list.status_code == 200
    ids = [c["id"] for c in resp_list.json().get("clients", [])]
    assert client_id_real not in ids, f"Cliente de REAL apareció en listado de DEMO: {ids}"

    # ── 6. Verificación positiva: desde REAL SÍ se ve ──
    resp_own = await client.get(
        f"/api/clients/{client_id_real}",
        headers={"Authorization": f"Bearer {token_real}"},
    )
    assert resp_own.status_code == 200, (
        f"Acceso propio tenant esperaba 200, obtuve {resp_own.status_code}: {resp_own.text}"
    )
