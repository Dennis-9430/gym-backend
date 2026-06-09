"""Tests for PR #1: Quick Security Wins.

Covers: ALLOWED_ORIGINS config, CORS middleware, re.escape in admin search,
isDemo in TenantCreate, and Swagger docs gating.
"""

import pytest
import pytest_asyncio
from typing import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.models.tenant import TenantCreate, SubscriptionPlan, SubscriptionStatus
from app.main import app
from app.database import get_database, Collections
from app.auth.utils import get_password_hash

TEST_DB_NAME = f"{settings.MONGODB_DB_NAME}_test_security"
SUPER_ADMIN_EMAIL = "sec@admin.com"
SUPER_ADMIN_PASSWORD = "SecAdmin123!"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1.1: ALLOWED_ORIGINS in config.py
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowedOrigins:
    """ALLOWED_ORIGINS must be an explicit list, not a wildcard."""

    def test_allowed_origins_is_list(self):
        """ALLOWED_ORIGINS should be a list type (not str '*' wildcard)."""
        origins = settings.ALLOWED_ORIGINS
        assert isinstance(origins, list), (
            f"Expected list, got {type(origins).__name__}: {origins!r}"
        )

    def test_allowed_origins_no_wildcard(self):
        """ALLOWED_ORIGINS must NOT contain '*' wildcard."""
        origins = settings.ALLOWED_ORIGINS
        assert "*" not in origins, (
            f"Wildcard '*' found in ALLOWED_ORIGINS: {origins}"
        )

    def test_allowed_origins_non_empty(self):
        """ALLOWED_ORIGINS must contain at least one explicit origin."""
        origins = settings.ALLOWED_ORIGINS
        assert len(origins) > 0, (
            f"ALLOWED_ORIGINS must not be empty: {origins}"
        )

    def test_allowed_origins_default_includes_production(self):
        """Default ALLOWED_ORIGINS should include production Vercel URL."""
        # Read the class default directly to verify the code change
        from app.config import Settings
        default_origins = Settings.model_fields["ALLOWED_ORIGINS"].default
        assert "https://gym-management-nine-azure.vercel.app" in default_origins, (
            f"Production URL missing from default: {default_origins}"
        )
        assert "http://localhost:5173" in default_origins, (
            f"Localhost URL missing from default: {default_origins}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1.4: isDemo in TenantCreate
# ═══════════════════════════════════════════════════════════════════════════════

class TestTenantCreateIsDemo:
    """TenantCreate must include isDemo field with default False."""

    def test_tenant_create_has_is_demo_field(self):
        """TenantCreate model should have isDemo field in model_fields."""
        assert "isDemo" in TenantCreate.model_fields, (
            "TenantCreate missing 'isDemo' field in model_fields"
        )

    def test_tenant_create_is_demo_default_false(self):
        """Creating TenantCreate without isDemo should default to False."""
        tenant = TenantCreate(
            email="test@demo.com",
            businessName="Test Gym",
            password="password123",
            ownerFirstName="Owner",
            ownerLastName="Test",
            plan=SubscriptionPlan.BASIC,
        )
        assert tenant.isDemo is False, (
            f"Expected isDemo=False by default, got {tenant.isDemo}"
        )

    def test_tenant_create_is_demo_can_be_true(self):
        """Creating TenantCreate with isDemo=True should store True."""
        tenant = TenantCreate(
            email="demo@demo.com",
            businessName="Demo Gym",
            password="password123",
            ownerFirstName="Demo",
            ownerLastName="User",
            plan=SubscriptionPlan.BASIC,
            isDemo=True,
        )
        assert tenant.isDemo is True, (
            f"Expected isDemo=True, got {tenant.isDemo}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1.5: Swagger docs gated on DEBUG
# ═══════════════════════════════════════════════════════════════════════════════

class TestSwaggerDocsGated:
    """Swagger docs /docs, /redoc, /openapi.json must be gated on DEBUG."""

    # Note: The app is created at module level in main.py with DEBUG=True (default).
    # We verify that docs_url is set when DEBUG=True.
    # A full integration test with DEBUG=False would require app recreation.

    def test_docs_url_configured_when_debug(self):
        """When DEBUG=True, docs_url should be '/docs'."""
        from app.main import app
        assert app.docs_url == "/docs", (
            f"Expected docs_url='/docs', got {app.docs_url!r}"
        )

    def test_redoc_url_configured_when_debug(self):
        """When DEBUG=True, redoc_url should be '/redoc'."""
        from app.main import app
        assert app.redoc_url == "/redoc", (
            f"Expected redoc_url='/redoc', got {app.redoc_url!r}"
        )

    def test_openapi_url_configured_when_debug(self):
        """When DEBUG=True, openapi_url should be '/openapi.json'."""
        from app.main import app
        assert app.openapi_url == "/openapi.json", (
            f"Expected openapi_url='/openapi.json', got {app.openapi_url!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures for CORS and admin search tests
# ═══════════════════════════════════════════════════════════════════════════════


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


@pytest_asyncio.fixture
async def seed_super_admin(test_db: AsyncIOMotorDatabase):
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
    resp = await client.post("/api/tenants/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD,
    })
    assert resp.status_code == 200, f"Login super admin: {resp.status_code} {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture
async def seed_tenants(test_db: AsyncIOMotorDatabase):
    """Crea tenants de prueba con names que contienen caracteres especiales."""
    tenants = [
        {
            "tenantId": "tenant-regex-001",
            "businessCode": "gym-regex",
            "businessName": "Gimnasio Regex (Test)",
            "email": "regex@gym.com",
            "plan": "BASIC",
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "subscriptionEndDate": None,
            "createdAt": "2026-01-01T00:00:00Z",
        },
        {
            "tenantId": "tenant-plus-002",
            "businessCode": "gym-plus+special",
            "businessName": "Gimnasio +Plus",
            "email": "plus@gym.com",
            "plan": "PREMIUM",
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "subscriptionEndDate": None,
            "createdAt": "2026-01-01T00:00:00Z",
        },
    ]
    await test_db[Collections.TENANTS].insert_many(tenants)
    return tenants


@pytest_asyncio.fixture
async def seed_employees(test_db: AsyncIOMotorDatabase):
    from bson import ObjectId
    employees = [
        {
            "_id": ObjectId("507f1f77bcf86cd799439999"),
            "tenantId": "tenant-regex-001",
            "username": "admin_regex",
            "email": "admin@regex.com",
            "firstName": "Admin",
            "lastName": "Regex",
            "role": "ADMIN",
            "isOwner": True,
            "status": "ACTIVE",
        },
    ]
    await test_db[Collections.EMPLOYEES].insert_many(employees)
    return employees


@pytest_asyncio.fixture
async def seed_users(test_db: AsyncIOMotorDatabase, seed_employees):
    from bson import ObjectId
    users = [
        {
            "username": "admin_regex",
            "password_hash": get_password_hash("password123"),
            "role": "ADMIN",
            "employeeId": "507f1f77bcf86cd799439999",
            "tenantId": "tenant-regex-001",
            "isOwner": True,
        },
    ]
    await test_db[Collections.USERS].insert_many(users)
    return users


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1.2: CORS middleware — explicit origins
# ═══════════════════════════════════════════════════════════════════════════════

class TestCORSMiddleware:
    """CORS middleware must only allow explicit origins, not reflect any."""

    ALLOWED_ORIGIN = "http://localhost:5173"
    BLOCKED_ORIGIN = "https://evil-site.com"

    @pytest.mark.asyncio
    async def test_cors_allows_known_origin(self, client):
        """Request from allowed origin receives CORS headers."""
        resp = await client.get(
            "/health",
            headers={"Origin": self.ALLOWED_ORIGIN},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == self.ALLOWED_ORIGIN, (
            f"Expected ACAO={self.ALLOWED_ORIGIN}, got {resp.headers.get('access-control-allow-origin')}"
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_cors_blocks_arbitrary_origin(self, client):
        """Request from arbitrary origin must NOT receive CORS headers."""
        resp = await client.get(
            "/health",
            headers={"Origin": self.BLOCKED_ORIGIN},
        )
        assert resp.status_code == 200
        # If origin not allowed, ACAO should NOT be set to the blocked origin
        acao = resp.headers.get("access-control-allow-origin")
        assert acao != self.BLOCKED_ORIGIN, (
            f"ACAO should not reflect blocked origin, got {acao}"
        )

    @pytest.mark.asyncio
    async def test_cors_preflight_allows_known_origin(self, client):
        """OPTIONS preflight from allowed origin should succeed with CORS."""
        resp = await client.options(
            "/health",
            headers={
                "Origin": self.ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == self.ALLOWED_ORIGIN
        assert resp.headers.get("access-control-allow-credentials") == "true"
        assert "GET" in resp.headers.get("access-control-allow-methods", "")

    @pytest.mark.asyncio
    async def test_cors_preflight_blocks_arbitrary_origin(self, client):
        """OPTIONS preflight from arbitrary origin must not reflect it."""
        resp = await client.options(
            "/health",
            headers={
                "Origin": self.BLOCKED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = resp.headers.get("access-control-allow-origin")
        assert acao != self.BLOCKED_ORIGIN, (
            f"Preflight ACAO should not reflect blocked origin, got {acao}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1.3: Escape regex in admin.py search
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminSearchReEscape:
    """Admin search must escape regex-special characters."""

    @pytest.mark.asyncio
    async def test_search_with_special_regex_chars_returns_results(
        self, client, seed_tenants, seed_employees, seed_users, super_admin_token
    ):
        """Search with '.' and '+' special regex chars should work without error."""
        resp = await client.get(
            "/api/admin/tenants?search=+Plus",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert resp.status_code == 200, (
            f"Search with special regex chars failed: {resp.status_code} {resp.text}"
        )
        data = resp.json()
        assert data["total"] >= 1, (
            f"Expected at least 1 result for '+Plus' search, got {data['total']}"
        )

    @pytest.mark.asyncio
    async def test_search_with_parentheses_returns_results(
        self, client, seed_tenants, seed_employees, seed_users, super_admin_token
    ):
        """Search with '()' special regex chars should work without error."""
        resp = await client.get(
            "/api/admin/tenants?search=(Test)",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert resp.status_code == 200, (
            f"Search with parentheses failed: {resp.status_code} {resp.text}"
        )
        data = resp.json()
        assert data["total"] >= 1, (
            f"Expected at least 1 result for '(Test)' search, got {data['total']}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PR #2: Error Handling & Info Leaks
# ═══════════════════════════════════════════════════════════════════════════════

class TestGlobalExceptionHandler:
    """Global exception handler must catch unhandled 500s and return generic JSON."""

    @pytest.mark.asyncio
    async def test_global_handler_returns_generic_json(self, client):
        """Unhandled exceptions must return 500 with generic error body."""
        from app.main import app

        # Register a temporary route that raises an unhandled exception
        @app.get("/test/trigger-500")
        async def _trigger_error():
            raise RuntimeError("secret internal detail")

        resp = await client.get("/test/trigger-500")
        assert resp.status_code == 500, (
            f"Expected 500, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert data == {"error": {"code": "INTERNAL_ERROR", "message": "Error interno del servidor"}}, (
            f"Unexpected response body: {data}"
        )

    @pytest.mark.asyncio
    async def test_global_handler_allows_existing_http_exceptions(self, client):
        """Existing HTTPException handlers must still work (not overridden)."""
        # /nonexistent-route triggers FastAPI's built-in 404 handler
        resp = await client.get("/api/nonexistent-route-test-12345")
        # FastAPI returns 404, not 500
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent route, got {resp.status_code}: {resp.text}"
        )


class TestErrorInfoLeaks:
    """Error responses must not leak internal exception details."""

    def test_no_str_e_in_api_error_messages(self):
        """Source code must not expose str(e) in API error response messages.

        This is a static-analysis safety net covering routers and services.
        str(e) is allowed in:
        - logger.* calls (internal logging)
        - DB storage fields (e.g. emailDelivery.errorMessage)
        - Internal processing (not returned to client)
        """
        import re
        from pathlib import Path

        base = Path("app")
        files_to_check = list(base.rglob("*.py"))

        # Allowlist patterns where str(e) is acceptable
        allowed_internal_patterns = [
            r'logger\.\w+\(.*str\(e\)',       # logger.error(... str(e) ...)
            r'errorMessage.*str\(e\)',          # DB storage field
            r'err_str\s*=\s*str\(e\)',          # Internal processing variable
        ]
        allowed_regex = re.compile('|'.join(allowed_internal_patterns))

        leaked = []
        for fpath in files_to_check:
            rel = fpath.relative_to(base.parent)
            text = fpath.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if 'str(e)' not in stripped:
                    continue
                # Skip if matching allowlist
                if allowed_regex.search(stripped):
                    continue
                leaked.append(f"{rel}:{i}: {stripped}")

        assert len(leaked) == 0, (
            f"Found {len(leaked)} potential info-leak pattern(s):\n"
            + "\n".join(leaked)
        )
