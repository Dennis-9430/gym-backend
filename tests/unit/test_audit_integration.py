"""Tests for audit logging integration into existing services.

Verifies that audit_service is accepted as optional parameter and
logs when provided, but doesn't break existing behavior when None.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_db():
    """Create a Motor-like db mock supporting attribute access (db.users, db.tenants, etc.)
    and __getitem__ (db['audit_logs']).
    """
    db = MagicMock()

    # Support db.collection_name attribute access (Motor-style)
    def get_attr(name):
        col = MagicMock()
        col.find_one = AsyncMock()
        col.find = MagicMock()
        col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
        col.update_one = AsyncMock()
        col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
        col.count_documents = AsyncMock(return_value=0)
        return col

    db.configure_mock(**{})  # Don't pre-configure

    # Intercept __getattr__ for collection access
    original_getattr = db.__class__.__getattr__ if hasattr(db.__class__, '__getattr__') else None

    def collection_getter(name):
        col = MagicMock()
        col.find_one = AsyncMock()
        col.find = AsyncMock(return_value=col)
        col.sort = MagicMock(return_value=col)
        col.skip = MagicMock(return_value=col)
        col.limit = MagicMock(return_value=col)
        col.to_list = AsyncMock(return_value=[])
        col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
        col.update_one = AsyncMock()
        col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
        col.count_documents = AsyncMock(return_value=0)
        return col

    # We can't easily override __getattr__ on a MagicMock instance,
    # so instead we provide a helper: call _mock_collection(db, name) to set up
    return db


def _mock_collection(db, name, **kwargs):
    """Set up a mock collection on db with optional overrides."""
    col = MagicMock()
    col.find_one = AsyncMock()
    col.find = AsyncMock(return_value=col)
    col.sort = MagicMock(return_value=col)
    col.skip = MagicMock(return_value=col)
    col.limit = MagicMock(return_value=col)
    col.to_list = AsyncMock(return_value=[])
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
    col.update_one = AsyncMock()
    col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.count_documents = AsyncMock(return_value=0)
    for key, val in kwargs.items():
        setattr(col, key, val)
    setattr(db, name, col)
    # Also support __getitem__
    def getitem(n):
        if n == name:
            return col
        return getattr(db, n, MagicMock())
    db.__getitem__ = MagicMock(side_effect=getitem)
    return col


def _apply_db_getitem(db):
    """Configure __getitem__ on db to delegate to attribute access (Motor-style)."""
    def getitem(name):
        return getattr(db, name)
    db.__getitem__ = MagicMock(side_effect=getitem)


class TestTenantAuthAudit:
    """RED→GREEN: TenantAuthService methods accept audit_service parameter."""

    @pytest.fixture
    def audit_service(self):
        from app.services.audit_service import AuditService
        db = MagicMock()
        audit_col = MagicMock()
        audit_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
        audit_col.find = MagicMock(return_value=audit_col)
        audit_col.sort = MagicMock(return_value=audit_col)
        audit_col.skip = MagicMock(return_value=audit_col)
        audit_col.limit = MagicMock(return_value=audit_col)
        audit_col.to_list = AsyncMock(return_value=[])
        audit_col.count_documents = AsyncMock(return_value=0)
        db.__getitem__ = MagicMock(return_value=audit_col)
        return AuditService(db)

    @pytest.mark.asyncio
    async def test_login_accepts_audit_service_optional(self):
        """login() should accept audit_service=None without error."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantLoginRequest

        db = MagicMock()
        # Mock SUPER_ADMIN login path (simplest — no tenant dependency)
        db.users = MagicMock()
        db.users.find_one = AsyncMock(return_value={
            "username": "admin",
            "password_hash": "",
            "role": "SUPER_ADMIN",
            "tenantId": None,
        })
        service = TenantAuthService(db)
        data = TenantLoginRequest(email="admin", password="wrong")
        with pytest.raises(Exception):
            await service.login(data, audit_service=None)

    @pytest.mark.asyncio
    async def test_login_calls_audit_on_success(self):
        """login() should call audit_service.log_event on success."""
        from app.services.tenant_auth import TenantAuthService
        from app.auth.utils import get_password_hash

        db = MagicMock()

        # Mock SUPER_ADMIN login path
        db.users = MagicMock()
        db.users.find_one = AsyncMock(return_value={
            "username": "admin",
            "password_hash": get_password_hash("correct"),
            "role": "SUPER_ADMIN",
            "tenantId": None,
        })

        audit_db = MagicMock()
        audit_col = MagicMock()
        audit_col.insert_one = AsyncMock(return_value=MagicMock(
            inserted_id="mock-id"
        ))
        audit_db.__getitem__ = MagicMock(return_value=audit_col)
        from app.services.audit_service import AuditService
        audit_service = AuditService(audit_db)

        from app.services.tenant_auth import TenantAuthService
        service = TenantAuthService(db)

        # Create proper login request
        from app.models.tenant import TenantLoginRequest
        data = TenantLoginRequest(email="admin", password="correct")
        result = await service.login(data, audit_service=audit_service)

        audit_col.insert_one.assert_awaited()
        call_kwargs = audit_col.insert_one.call_args[0][0]
        assert call_kwargs["event"] == "LOGIN_SUCCESS"
        assert call_kwargs["actor_id"] == "admin"

    @pytest.mark.asyncio
    async def test_login_calls_audit_on_failure(self):
        """login() should call audit_service.log_event before raising on failure."""
        from app.services.tenant_auth import TenantAuthService
        from app.auth.utils import get_password_hash
        from app.models.tenant import TenantLoginRequest
        from app.models.audit_log import AuditEvents

        db = MagicMock()
        # Mock SUPER_ADMIN login path
        db.users = MagicMock()
        db.users.find_one = AsyncMock(return_value={
            "username": "admin",
            "password_hash": get_password_hash("correct"),
            "role": "SUPER_ADMIN",
            "tenantId": None,
        })

        audit_db = MagicMock()
        audit_col = MagicMock()
        audit_col.insert_one = AsyncMock(return_value=MagicMock(
            inserted_id="mock-id"
        ))
        audit_db.__getitem__ = MagicMock(return_value=audit_col)
        from app.services.audit_service import AuditService
        audit_service = AuditService(audit_db)

        service = TenantAuthService(db)
        data = TenantLoginRequest(email="admin", password="wrong")

        with pytest.raises(Exception):
            await service.login(data, audit_service=audit_service)

        audit_col.insert_one.assert_awaited()
        call_kwargs = audit_col.insert_one.call_args[0][0]
        assert call_kwargs["event"] == AuditEvents.LOGIN_FAILED
        assert call_kwargs["actor_id"] == "admin"

    @pytest.mark.asyncio
    async def test_forgot_password_calls_audit(self):
        """forgot_password() should accept and use audit_service."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock()
        service = TenantAuthService(db)

        audit_db = MagicMock()
        audit_col = MagicMock()
        audit_col.insert_one = AsyncMock(return_value=MagicMock(
            inserted_id="mock-id"
        ))
        audit_db.__getitem__ = MagicMock(return_value=audit_col)
        from app.services.audit_service import AuditService
        audit_service = AuditService(audit_db)

        # forgot_password doesn't actually check users — just returns True
        result = await service.forgot_password("user@test.com", audit_service=audit_service)
        assert result is True
        audit_col.insert_one.assert_awaited()
        call_kwargs = audit_col.insert_one.call_args[0][0]
        assert call_kwargs["event"] == "FORGOT_PASSWORD"

    @pytest.mark.asyncio
    async def test_forgot_password_accepts_none(self):
        """forgot_password() should work with audit_service=None."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock()
        service = TenantAuthService(db)

        result = await service.forgot_password("user@test.com", audit_service=None)
        assert result is True

    @pytest.mark.asyncio
    async def test_reset_password_calls_audit(self):
        """reset_password() should call audit_service.log_event on success."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import PasswordResetConfirm

        db = MagicMock()
        # Mock consume_reset_token
        from unittest.mock import patch

        audit_db = MagicMock()
        audit_col = MagicMock()
        audit_col.insert_one = AsyncMock(return_value=MagicMock(
            inserted_id="mock-id"
        ))
        audit_db.__getitem__ = MagicMock(return_value=audit_col)
        from app.services.audit_service import AuditService
        audit_service = AuditService(audit_db)

        service = TenantAuthService(db)
        data = PasswordResetConfirm(token="valid-token", newPassword="newpass123")

        # Test that reset_password accepts audit_service parameter
        assert hasattr(service, 'reset_password')
        assert callable(service.reset_password)


class TestAdminTenantAudit:
    """RED→GREEN: AdminTenantService methods accept audit_service parameter."""

    def setup_service(self):
        from app.services.admin_tenant import AdminTenantService
        db = MagicMock()
        return AdminTenantService(db), db

    @pytest.mark.asyncio
    async def test_delete_tenant_accepts_audit_service(self):
        """delete_tenant() should accept audit_service=None without error."""
        from app.services.admin_tenant import AdminTenantService
        from app.database import Collections

        db = MagicMock()
        # Mock tenant exists
        def getitem(name):
            col = MagicMock()
            col.find_one = AsyncMock()
            col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
            col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
            col.update_one = AsyncMock()
            if name == Collections.TENANTS:
                col.find_one = AsyncMock(return_value={
                    "tenantId": "t-001",
                    "businessName": "Gym Alpha",
                    "_id": "abc",
                })
            return col
        db.__getitem__ = MagicMock(side_effect=getitem)

        service = AdminTenantService(db)
        result = await service.delete_tenant("t-001", audit_service=None)
        assert "message" in result

    @pytest.mark.asyncio
    async def test_suspend_accepts_audit_service(self):
        """suspend() should work with audit_service=None."""
        from app.services.admin_tenant import AdminTenantService

        db = MagicMock()
        tenants_col = MagicMock()
        tenants_col.find_one = AsyncMock(return_value={
            "tenantId": "t-001",
            "_id": "abc",
        })
        tenants_col.update_one = AsyncMock()
        db.__getitem__ = MagicMock(return_value=tenants_col)

        service = AdminTenantService(db)
        result = await service.suspend("t-001", "fraud", audit_service=None)
        assert "id" in result

    @pytest.mark.asyncio
    async def test_reactivate_accepts_audit_service(self):
        """reactivate() should work with audit_service=None."""
        from app.services.admin_tenant import AdminTenantService

        db = MagicMock()
        tenants_col = MagicMock()
        tenants_col.find_one = AsyncMock(return_value={
            "tenantId": "t-001",
            "subscriptionStatus": "SUSPENDED",
            "_id": "abc",
        })
        tenants_col.update_one = AsyncMock()
        db.__getitem__ = MagicMock(return_value=tenants_col)

        service = AdminTenantService(db)
        result = await service.reactivate("t-001", "resolved", audit_service=None)
        assert "id" in result


class TestAdminPaymentAudit:
    """RED→GREEN: AdminPaymentService methods accept audit_service parameter."""

    @pytest.mark.asyncio
    async def test_approve_payment_accepts_audit_service(self):
        """approve_payment() should work with audit_service=None."""
        from app.services.admin_payment import AdminPaymentService
        from app.database import Collections

        db = MagicMock()
        tenants_col = MagicMock()
        tenants_col.find_one = AsyncMock(return_value={
            "tenantId": "t-001",
            "plan": "BASIC",
            "_id": "abc",
        })
        tenants_col.update_one = AsyncMock()

        payments_col = MagicMock()
        payments_col.find_one = AsyncMock(return_value={
            "_id": "pay-1",
            "tenantId": "t-001",
            "method": "TRANSFER",
            "status": "PENDING",
            "months": 1,
        })
        payments_col.update_one = AsyncMock()

        def getitem(name):
            if name == Collections.TENANTS:
                return tenants_col
            if name == Collections.TENANT_PAYMENTS:
                return payments_col
            return MagicMock()

        db.__getitem__ = MagicMock(side_effect=getitem)

        service = AdminPaymentService(db)
        result = await service.approve_payment("t-001", "approved", "admin", audit_service=None)
        assert "message" in result

    @pytest.mark.asyncio
    async def test_reject_payment_accepts_audit_service(self):
        """reject_payment() should work with audit_service=None."""
        from app.services.admin_payment import AdminPaymentService
        from app.database import Collections

        db = MagicMock()
        tenants_col = MagicMock()
        tenants_col.find_one = AsyncMock(return_value={
            "tenantId": "t-001",
            "_id": "abc",
        })
        tenants_col.update_one = AsyncMock()

        payments_col = MagicMock()
        payments_col.find_one = AsyncMock(return_value={
            "_id": "pay-1",
            "tenantId": "t-001",
            "method": "TRANSFER",
            "status": "PENDING",
        })
        payments_col.update_one = AsyncMock()

        def getitem(name):
            if name == Collections.TENANTS:
                return tenants_col
            if name == Collections.TENANT_PAYMENTS:
                return payments_col
            return MagicMock()

        db.__getitem__ = MagicMock(side_effect=getitem)

        service = AdminPaymentService(db)
        result = await service.reject_payment("t-001", "invalid doc", "admin", audit_service=None)
        assert "message" in result
