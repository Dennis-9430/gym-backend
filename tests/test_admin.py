"""Tests para el módulo SUPER_ADMIN + pagos manuales.

Cubre: login SUPER_ADMIN, autorización, CRUD de tenants, pagos manuales,
suspender/cancelar/reactivar, PENDING_PAYMENT en registro.
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
from app.models.tenant import SubscriptionStatus

TEST_DB_NAME = f"{settings.MONGODB_DB_NAME}_test"

SUPER_ADMIN_EMAIL = "super@gymadmin.com"
SUPER_ADMIN_PASSWORD = "SuperAdmin123!"


# ── Fixtures (function-scoped) ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def mongo_client() -> AsyncGenerator[AsyncIOMotorClient, None]:
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    yield client
    await client.drop_database(TEST_DB_NAME)
    client.close()


@pytest_asyncio.fixture
async def test_db(mongo_client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    return mongo_client[TEST_DB_NAME]


@pytest_asyncio.fixture(autouse=True)
async def clean_test_db(mongo_client: AsyncIOMotorClient):
    db = mongo_client[TEST_DB_NAME]
    for col in await db.list_collection_names():
        if not col.startswith("system."):
            await db[col].delete_many({})


@pytest_asyncio.fixture
async def init_global_db(
    mongo_client: AsyncIOMotorClient,
    test_db: AsyncIOMotorDatabase,
):
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Seed data ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_tenants(test_db: AsyncIOMotorDatabase):
    """Crea tenants de prueba con distintos estados."""
    tenants = [
        {
            "tenantId": "tenant-active-001",
            "businessCode": "gym-activo",
            "businessName": "Gimnasio Activo",
            "email": "activo@gym.com",
            "plan": "BASIC",
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "subscriptionEndDate": None,
            "createdAt": "2026-01-01T00:00:00Z",
        },
        {
            "tenantId": "tenant-pending-002",
            "businessCode": "gym-pendiente",
            "businessName": "Gimnasio Pendiente",
            "email": "pendiente@gym.com",
            "plan": "BASIC",
            "subscriptionStatus": SubscriptionStatus.PENDING_PAYMENT,
            "subscriptionEndDate": None,
            "createdAt": "2026-02-01T00:00:00Z",
        },
        {
            "tenantId": "tenant-suspended-003",
            "businessCode": "gym-suspendido",
            "businessName": "Gimnasio Suspendido",
            "email": "suspendido@gym.com",
            "plan": "PREMIUM",
            "subscriptionStatus": SubscriptionStatus.SUSPENDED,
            "subscriptionEndDate": "2026-03-01T00:00:00Z",
            "createdAt": "2026-01-15T00:00:00Z",
        },
        {
            "tenantId": "tenant-expired-004",
            "businessCode": "gym-expirado",
            "businessName": "Gimnasio Expirado",
            "email": "expirado@gym.com",
            "plan": "BASIC",
            "subscriptionStatus": SubscriptionStatus.EXPIRED,
            "subscriptionEndDate": "2026-01-01T00:00:00Z",
            "createdAt": "2025-12-01T00:00:00Z",
        },
        {
            "tenantId": "tenant-cancelled-005",
            "businessCode": "gym-cancelado",
            "businessName": "Gimnasio Cancelado",
            "email": "cancelado@gym.com",
            "plan": "BASIC",
            "subscriptionStatus": SubscriptionStatus.CANCELLED,
            "subscriptionEndDate": None,
            "createdAt": "2026-01-10T00:00:00Z",
        },
    ]
    await test_db[Collections.TENANTS].insert_many(tenants)
    return tenants


@pytest_asyncio.fixture
async def seed_employees(test_db: AsyncIOMotorDatabase):
    """Crea employees básicos para los tenants de prueba."""
    from bson import ObjectId

    employees = [
        {
            "_id": ObjectId("507f1f77bcf86cd799439101"),
            "tenantId": "tenant-active-001",
            "username": "admin_activo",
            "email": "admin@activo.com",
            "firstName": "Admin",
            "lastName": "Activo",
            "role": "ADMIN",
            "isOwner": True,
            "status": "ACTIVE",
        },
    ]
    await test_db[Collections.EMPLOYEES].insert_many(employees)
    return employees


@pytest_asyncio.fixture
async def seed_users(test_db: AsyncIOMotorDatabase, seed_employees):
    """Crea usuarios en colección users para autenticación."""
    from bson import ObjectId

    users = [
        {
            "username": "admin_activo",
            "password_hash": get_password_hash("password123"),
            "role": "ADMIN",
            "employeeId": "507f1f77bcf86cd799439101",
            "tenantId": "tenant-active-001",
            "isOwner": True,
        },
    ]
    await test_db[Collections.USERS].insert_many(users)
    return users


@pytest_asyncio.fixture
async def seed_super_admin(test_db: AsyncIOMotorDatabase):
    """Crea el usuario SUPER_ADMIN en la colección users."""
    user = {
        "username": SUPER_ADMIN_EMAIL,
        "password_hash": get_password_hash(SUPER_ADMIN_PASSWORD),
        "role": "SUPER_ADMIN",
        "tenantId": None,
        "isOwner": False,
    }
    await test_db[Collections.USERS].insert_one(user)
    return user


@pytest_asyncio.fixture
async def super_admin_token(client, seed_super_admin):
    """Obtiene token JWT para SUPER_ADMIN."""
    resp = await client.post("/api/tenants/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD,
    })
    assert resp.status_code == 200, f"Login super admin: {resp.status_code} {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture
async def regular_token(client, seed_tenants, seed_employees, seed_users):
    """Obtiene token JWT para un usuario regular (ADMIN de tenant)."""
    resp = await client.post("/api/tenants/login", json={
        "email": "admin_activo",
        "password": "password123",
        "businessCode": "gym-activo",
    })
    assert resp.status_code == 200, f"Login regular: {resp.status_code} {resp.text}"
    return resp.json()["accessToken"]


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_super_admin_login(client, seed_super_admin):
    """SUPER_ADMIN puede loguearse con email+password y recibe token."""
    resp = await client.post("/api/tenants/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD,
    })
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "accessToken" in data
    assert data["tenant"]["businessName"] == "System Administrator"


@pytest.mark.asyncio
async def test_super_admin_login_no_business_code(client, seed_super_admin):
    """SUPER_ADMIN puede loguearse SIN businessCode."""
    # Sin businessCode ni tenantId
    resp = await client.post("/api/tenants/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD,
    })
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "accessToken" in data


@pytest.mark.asyncio
async def test_non_super_admin_gets_403(client, regular_token):
    """Usuario regular recibe 403 al acceder a endpoint de admin."""
    endpoints = [
        ("GET", "/api/admin/dashboard"),
        ("GET", "/api/admin/tenants"),
        ("GET", "/api/admin/tenants/tenant-active-001"),
        ("POST", "/api/admin/tenants/tenant-active-001/manual-payment"),
        ("POST", "/api/admin/tenants/tenant-active-001/suspend"),
        ("POST", "/api/admin/tenants/tenant-active-001/cancel"),
        ("POST", "/api/admin/tenants/tenant-active-001/reactivate"),
        ("GET", "/api/admin/tenants/tenant-active-001/payments"),
    ]
    for method, path in endpoints:
        if method == "GET":
            resp = await client.get(path, headers={"Authorization": f"Bearer {regular_token}"})
        else:
            resp = await client.post(path, json={}, headers={"Authorization": f"Bearer {regular_token}"})
        assert resp.status_code == 403, (
            f"{method} {path} esperaba 403, obtuvo {resp.status_code}: {resp.text}"
        )
        assert "SUPER_ADMIN" in resp.json()["detail"].upper()


@pytest.mark.asyncio
async def test_list_tenants_as_super_admin(client, seed_tenants, super_admin_token):
    """SUPER_ADMIN puede listar todos los tenants."""
    resp = await client.get(
        "/api/admin/tenants",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    assert data["page"] == 1
    assert data["limit"] == 20

    # Verificar filtro por status
    resp = await client.get(
        "/api/admin/tenants?status=ACTIVE",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # Verificar filtro por search
    resp = await client.get(
        "/api/admin/tenants?search=Pendiente",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_manual_payment_activates_tenant(
    client, seed_tenants, super_admin_token
):
    """Registrar pago manual → tenant pasa a ACTIVE con subscriptionEndDate."""
    tenant_id = "tenant-pending-002"

    # Verificar estado inicial
    resp = await client.get(
        f"/api/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["subscriptionStatus"] == SubscriptionStatus.PENDING_PAYMENT

    # Registrar pago manual
    from datetime import datetime, timedelta
    resp = await client.post(
        f"/api/admin/tenants/{tenant_id}/manual-payment",
        json={
            "plan": "BASIC",
            "months": 3,
            "amount": 60.0,
            "currency": "USD",
            "method": "CASH",
            "reference": "PAGO-001",
            "notes": "Pago de prueba",
        },
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    payment = resp.json()
    assert payment["tenantId"] == tenant_id
    assert payment["plan"] == "BASIC"
    assert payment["months"] == 3
    assert payment["amount"] == 60.0
    assert payment["method"] == "CASH"
    assert payment["reference"] == "PAGO-001"

    # Verificar que el tenant ahora está ACTIVE
    resp = await client.get(
        f"/api/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    tenant = resp.json()
    assert tenant["subscriptionStatus"] == SubscriptionStatus.ACTIVE
    assert tenant["subscriptionEndDate"] is not None
    assert tenant["plan"] == "BASIC"


@pytest.mark.asyncio
async def test_payment_history_recorded(
    client, seed_tenants, super_admin_token
):
    """Los pagos registrados aparecen en el historial del tenant."""
    tenant_id = "tenant-pending-002"

    # Registrar 2 pagos
    for i in range(2):
        resp = await client.post(
            f"/api/admin/tenants/{tenant_id}/manual-payment",
            json={
                "plan": "BASIC",
                "months": 1,
                "amount": 20.0 + i,
                "currency": "USD",
                "method": "CASH",
                "reference": f"PAGO-{i:03d}",
            },
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert resp.status_code == 200

    # Verificar historial
    resp = await client.get(
        f"/api/admin/tenants/{tenant_id}/payments",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Verificar orden descendente (más reciente primero)
    assert data["items"][0]["reference"] == "PAGO-001"
    assert data["items"][1]["reference"] == "PAGO-000"


@pytest.mark.asyncio
async def test_suspend_tenant(client, seed_tenants, super_admin_token):
    """Suspender tenant → status SUSPENDED."""
    tenant_id = "tenant-active-001"

    resp = await client.post(
        f"/api/admin/tenants/{tenant_id}/suspend",
        json={"reason": "Morosidad"},
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    assert resp.json()["subscriptionStatus"] == SubscriptionStatus.SUSPENDED


@pytest.mark.asyncio
async def test_cancel_tenant(client, seed_tenants, super_admin_token):
    """Cancelar tenant activo → status CANCELLED. Cancelar CANCELLED → 400."""
    # Cancelar tenant activo
    resp = await client.post(
        f"/api/admin/tenants/tenant-active-001/cancel",
        json={"reason": "Baja voluntaria"},
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    assert resp.json()["subscriptionStatus"] == SubscriptionStatus.CANCELLED

    # Intentar cancelar un tenant ya CANCELLED
    resp = await client.post(
        f"/api/admin/tenants/tenant-cancelled-005/cancel",
        json={"reason": "otra vez"},
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 400, f"Esperaba 400, obtuve {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_reactivate_tenant(client, seed_tenants, super_admin_token):
    """Reactivar tenant suspendido → ACTIVE. Reactivar ACTIVE → 400."""
    # Reactivar suspendido
    resp = await client.post(
        f"/api/admin/tenants/tenant-suspended-003/reactivate",
        json={"reason": "Pago recibido"},
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    assert resp.json()["subscriptionStatus"] == SubscriptionStatus.ACTIVE

    # Reactivar expirado
    resp = await client.post(
        f"/api/admin/tenants/tenant-expired-004/reactivate",
        json={"reason": "Renovación"},
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["subscriptionStatus"] == SubscriptionStatus.ACTIVE

    # Intentar reactivar un tenant ACTIVE
    resp = await client.post(
        f"/api/admin/tenants/tenant-active-001/reactivate",
        json={"reason": "ya activo"},
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_tenant_pending_payment(client, super_admin_token):
    """Nuevo registro de tenant → PENDING_PAYMENT, login bloqueado."""
    from app.models.tenant import TenantCreate, SubscriptionPlan
    from app.auth.utils import get_password_hash

    # Registrar tenant
    resp = await client.post("/api/tenants/register", json={
        "email": "nuevo@gym.com",
        "businessName": "Gimnasio Nuevo",
        "password": "password123",
        "plan": "BASIC",
        "ownerFirstName": "Owner",
        "ownerLastName": "Nuevo",
    })
    assert resp.status_code == 201, f"Esperaba 201, obtuve {resp.status_code}: {resp.text}"
    tenant = resp.json()
    assert tenant["subscriptionStatus"] == SubscriptionStatus.PENDING_PAYMENT

    # Intentar login (debería fallar por PENDING_PAYMENT)
    resp = await client.post("/api/tenants/login", json={
        "email": "nuevo@gym.com",
        "password": "password123",
        "businessCode": "gimnasio-nuevo",
    })
    assert resp.status_code == 403, f"Esperaba 403, obtuve {resp.status_code}: {resp.text}"
    assert "inactiva" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_super_admin_dashboard(client, seed_tenants, super_admin_token):
    """SUPER_ADMIN puede ver estadísticas del dashboard."""
    resp = await client.get(
        "/api/admin/dashboard",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200, f"Esperaba 200, obtuve {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["total_tenants"] == 5
    assert data["active"] == 1
    assert data["pending_payment"] == 1
    assert data["suspended"] == 1
    assert data["cancelled"] == 1
    assert data["expired"] == 1
    assert data["monthly_revenue"] == 0.0  # Sin pagos registrados


@pytest.mark.asyncio
async def test_get_tenant_detail(client, seed_tenants, super_admin_token):
    """SUPER_ADMIN puede ver detalle completo de un tenant con resumen de pagos."""
    resp = await client.get(
        "/api/admin/tenants/tenant-active-001",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenantId"] == "tenant-active-001"
    assert data["businessName"] == "Gimnasio Activo"
    assert "total_paid" in data
    assert "last_payment_date" in data

    # Tenant inexistente → 404
    resp = await client.get(
        "/api/admin/tenants/no-existe",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 404
