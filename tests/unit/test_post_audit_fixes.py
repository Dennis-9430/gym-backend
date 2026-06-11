"""Tests for post-audit fixes.

Covers:
1. Fix 1: login_tenant passes audit_service to auth_service.login
2. Fix 2: get_tenant_from_request importable from app.api.dependencies
3. Fix 3: REGISTRATION_WHITELIST in settings
4. Fix 4: SalesService extracted from sales.py
5. Fix 5: RedisRateLimitStore class exists
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fix 1: Login audit ─────────────────────────────────────────────────────

class TestLoginAudit:
    """RED: login_tenant must create AuditService and pass to auth_service.login."""

    @pytest.mark.asyncio
    async def test_login_tenant_passes_audit_service(self):
        """login_tenant should create AuditService and pass to auth_service.login."""
        from app.routers.tenants import login_tenant
        from app.models.tenant import TenantLoginRequest
        from fastapi import Response

        mock_db = MagicMock()

        with patch("app.routers.tenants.get_database", return_value=mock_db):
            with patch("app.routers.tenants.AuditService") as mock_audit_cls:
                with patch("app.routers.tenants.TenantAuthService") as mock_auth_cls:
                    mock_auth = MagicMock()
                    mock_auth.login = AsyncMock(return_value={
                        "access_token": "test-token",
                        "tenant": {
                            "id": "t1", "tenantId": "t1",
                            "email": "a@b.com", "businessName": "Gym",
                            "plan": "BASIC", "subscriptionStatus": "ACTIVE",
                        },
                    })
                    mock_auth_cls.return_value = mock_auth

                    response = Response()
                    data = TenantLoginRequest(email="a@b.com", password="pass", tenantId="t1")
                    await login_tenant(data, response)

                    # Verify AuditService was created with db
                    mock_audit_cls.assert_called_once_with(mock_db)
                    # Verify login received audit_service
                    _, kwargs = mock_auth.login.call_args
                    assert "audit_service" in kwargs
                    assert kwargs["audit_service"] is mock_audit_cls.return_value


# ── Fix 2: Tenant auth import update ───────────────────────────────────────

class TestTenantAuthImports:
    """RED: get_tenant_from_request should be importable from app.api.dependencies."""

    def test_get_tenant_from_request_importable(self):
        """get_tenant_from_request should be importable from app.api.dependencies."""
        from app.api.dependencies import get_tenant_from_request
        assert callable(get_tenant_from_request)

    def test_old_import_not_available(self):
        """get_tenant_from_header_tenants should NOT exist in app.services.tenant_auth."""
        import app.services.tenant_auth
        assert not hasattr(app.services.tenant_auth, "get_tenant_from_header_tenants")


# ── Fix 3: REGISTRATION_WHITELIST in settings ──────────────────────────────

class TestRegistrationWhitelistConfig:
    """RED: REGISTRATION_WHITELIST must be in settings."""

    def test_registration_whitelist_exists_in_settings(self):
        """settings should have REGISTRATION_WHITELIST attribute."""
        from app.config import settings
        assert hasattr(settings, "REGISTRATION_WHITELIST")

    def test_registration_whitelist_is_set(self):
        """REGISTRATION_WHITELIST should be a set with expected email."""
        from app.config import settings
        assert isinstance(settings.REGISTRATION_WHITELIST, set)
        assert "dennischapu94@gmail.com" in settings.REGISTRATION_WHITELIST

    def test_router_uses_settings_whitelist(self):
        """tenants.py should use settings.REGISTRATION_WHITELIST, not hardcoded."""
        import app.routers.tenants
        # Verify no module-level REGISTRATION_WHITELIST
        assert not hasattr(app.routers.tenants, "REGISTRATION_WHITELIST")


# ── Fix 4: SalesService extraction ─────────────────────────────────────────

class TestSalesService:
    """RED: SalesService class must exist and expose expected methods."""

    def test_sales_service_module_importable(self):
        """SalesService module should be importable."""
        import app.services.sales_service
        assert app.services.sales_service is not None

    def test_sales_service_class_exists(self):
        """SalesService class should be exposed."""
        from app.services.sales_service import SalesService
        assert SalesService is not None

    def test_constructor_accepts_db(self):
        """SalesService constructor should accept AsyncIOMotorDatabase."""
        from app.services.sales_service import SalesService
        from motor.motor_asyncio import AsyncIOMotorDatabase
        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = SalesService(db)
        assert service.db is db

    def test_list_sales_method_exists(self):
        """SalesService should have list_sales method."""
        from app.services.sales_service import SalesService
        db = MagicMock()
        service = SalesService(db)
        assert hasattr(service, "list_sales")
        assert callable(service.list_sales)

    def test_get_sale_method_exists(self):
        """SalesService should have get_sale method."""
        from app.services.sales_service import SalesService
        db = MagicMock()
        service = SalesService(db)
        assert hasattr(service, "get_sale")
        assert callable(service.get_sale)

    def test_create_sale_method_exists(self):
        """SalesService should have create_sale method."""
        from app.services.sales_service import SalesService
        db = MagicMock()
        service = SalesService(db)
        assert hasattr(service, "create_sale")
        assert callable(service.create_sale)

    def test_update_sale_method_exists(self):
        """SalesService should have update_sale method."""
        from app.services.sales_service import SalesService
        db = MagicMock()
        service = SalesService(db)
        assert hasattr(service, "update_sale")
        assert callable(service.update_sale)

    def test_delete_sale_method_exists(self):
        """SalesService should have delete_sale method."""
        from app.services.sales_service import SalesService
        db = MagicMock()
        service = SalesService(db)
        assert hasattr(service, "delete_sale")
        assert callable(service.delete_sale)

    def test_update_voucher_method_exists(self):
        """SalesService should have update_voucher method."""
        from app.services.sales_service import SalesService
        db = MagicMock()
        service = SalesService(db)
        assert hasattr(service, "update_voucher")
        assert callable(service.update_voucher)

    def test_verify_payment_method_exists(self):
        """SalesService should have verify_payment method."""
        from app.services.sales_service import SalesService
        db = MagicMock()
        service = SalesService(db)
        assert hasattr(service, "verify_payment")
        assert callable(service.verify_payment)

    def test_router_still_exports_serialize_sale(self):
        """sales.py router should still export serialize_sale."""
        from app.routers.sales import serialize_sale
        assert callable(serialize_sale)

    def test_router_still_has_all_endpoints(self):
        """sales.py router should still have all endpoint functions."""
        from app.routers.sales import router, list_sales, get_sale, create_sale
        from app.routers.sales import update_sale, delete_sale, update_voucher, verify_payment
        assert callable(list_sales)
        assert callable(get_sale)
        assert callable(create_sale)
        assert callable(update_sale)
        assert callable(delete_sale)
        assert callable(update_voucher)
        assert callable(verify_payment)


# ── Fix 5: Redis rate limit store ──────────────────────────────────────────

class TestRedisRateLimitStore:
    """RED: RedisRateLimitStore class must exist."""

    def test_redis_rate_limit_store_class_exists(self):
        """RedisRateLimitStore should be importable."""
        from app.middleware.rate_limit_store import RedisRateLimitStore
        assert RedisRateLimitStore is not None

    def test_redis_store_extends_abstract(self):
        """RedisRateLimitStore should extend RateLimitStore."""
        from app.middleware.rate_limit_store import RedisRateLimitStore, RateLimitStore
        assert issubclass(RedisRateLimitStore, RateLimitStore)

    def test_redis_store_has_check_and_increment(self):
        """RedisRateLimitStore should have check_and_increment method."""
        from app.middleware.rate_limit_store import RedisRateLimitStore
        store = RedisRateLimitStore()
        assert hasattr(store, "check_and_increment")
        assert callable(store.check_and_increment)

    def test_redis_store_accepts_redis_url(self):
        """RedisRateLimitStore should accept redis_url parameter."""
        from app.middleware.rate_limit_store import RedisRateLimitStore
        store = RedisRateLimitStore(redis_url="redis://test:6379/0")
        assert store.redis_url == "redis://test:6379/0"

    def test_redis_config_exists_in_settings(self):
        """Settings should have REDIS_URL and REDIS_RATE_LIMIT_ENABLED."""
        from app.config import settings
        assert hasattr(settings, "REDIS_URL")
        assert hasattr(settings, "REDIS_RATE_LIMIT_ENABLED")

    def test_get_store_uses_settings_for_redis(self):
        """get_store should return RedisRateLimitStore when configured."""
        from app.middleware.rate_limit import get_store, set_store
        from app.middleware.rate_limit_store import RedisRateLimitStore

        # Reset store first
        set_store(None)

        with patch("app.middleware.rate_limit.settings") as mock_settings:
            mock_settings.REDIS_RATE_LIMIT_ENABLED = True
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            store = get_store()
            assert isinstance(store, RedisRateLimitStore)
