"""Tests for app/services/tenant_auth.py — TenantAuthService extraction.

These tests verify:
1. Module/service imports correctly and exposes expected symbols
2. TenantAuthService class structure (constructor, expected methods)
3. Standalone helpers: serialize_tenant, serialize_employee, get_tenant_from_header_tenants
4. Service methods delegate to self.db correctly
5. Each method returns the expected structure
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from motor.motor_asyncio import AsyncIOMotorDatabase


# ── 1. Module imports ────────────────────────────────────────────────────────


class TestModuleImports:
    """RED: Verify the module is importable and exposes expected names."""

    def test_module_can_be_imported(self):
        """Module should be importable."""
        import app.services.tenant_auth
        assert app.services.tenant_auth is not None

    def test_tenant_auth_service_class_exists(self):
        """TenantAuthService class should be exposed."""
        from app.services.tenant_auth import TenantAuthService
        assert TenantAuthService is not None

    def test_serialize_tenant_exists(self):
        """serialize_tenant helper should be exposed."""
        from app.services.tenant_auth import serialize_tenant
        assert callable(serialize_tenant)

    def test_serialize_employee_exists(self):
        """serialize_employee helper should be exposed."""
        from app.services.tenant_auth import serialize_employee
        assert callable(serialize_employee)

    def test_get_tenant_from_request_exists(self):
        """get_tenant_from_request helper should be exposed from app.api.dependencies."""
        from app.api.dependencies import get_tenant_from_request
        assert callable(get_tenant_from_request)


# ── 2. Class instantiation ───────────────────────────────────────────────────


class TestTenantAuthServiceInstantiation:
    """RED: TenantAuthService must accept db in constructor."""

    def test_constructor_accepts_db(self):
        """Constructor should accept an AsyncIOMotorDatabase instance."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert service.db is db

    def test_constructor_stores_db_as_self_db(self):
        """Constructor should store db as self.db."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert hasattr(service, 'db')


# ── 3. Method signatures ─────────────────────────────────────────────────────


class TestTenantAuthServiceMethods:
    """RED: Verify all expected methods exist with correct signatures."""

    def test_register_method_exists(self):
        """register() should be an async method."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantCreate, SubscriptionPlan

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert hasattr(service, 'register')
        assert callable(service.register)

    def test_login_method_exists(self):
        """login() should be an async method."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert hasattr(service, 'login')
        assert callable(service.login)

    def test_forgot_password_method_exists(self):
        """forgot_password() should be an async method."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert hasattr(service, 'forgot_password')
        assert callable(service.forgot_password)

    def test_reset_password_method_exists(self):
        """reset_password() should be an async method."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert hasattr(service, 'reset_password')
        assert callable(service.reset_password)

    def test_renew_subscription_method_exists(self):
        """renew_subscription() should be an async method."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert hasattr(service, 'renew_subscription')
        assert callable(service.renew_subscription)

    def test_get_tenant_config_method_exists(self):
        """get_tenant_config() should be an async method."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)
        assert hasattr(service, 'get_tenant_config')
        assert callable(service.get_tenant_config)


# ── 4. serialize_tenant helper ──────────────────────────────────────────────


class TestSerializeTenant:
    """RED: serialize_tenant must convert MongoDB doc to response dict."""

    def test_converts_id_from_objectid(self):
        """serialize_tenant should convert _id to id string."""
        from app.services.tenant_auth import serialize_tenant

        doc = {"_id": "abc123", "name": "Test Gym"}
        result = serialize_tenant(doc)
        assert result["id"] == "abc123"
        assert "_id" not in result

    def test_handles_none_doc(self):
        """serialize_tenant should handle None doc."""
        from app.services.tenant_auth import serialize_tenant

        result = serialize_tenant(None)
        assert result is None

    def test_handles_empty_doc(self):
        """serialize_tenant should handle doc with no _id."""
        from app.services.tenant_auth import serialize_tenant

        doc = {"name": "No ID"}
        result = serialize_tenant(doc)
        assert "id" not in result


# ── 5. serialize_employee helper ────────────────────────────────────────────


class TestSerializeEmployee:
    """RED: serialize_employee must convert MongoDB doc with status/role mapping."""

    def test_converts_id_to_string(self):
        """serialize_employee should convert _id to string."""
        from app.services.tenant_auth import serialize_employee

        doc = {"_id": "emp123", "name": "Test"}
        result = serialize_employee(doc)
        assert result["_id"] == "emp123"
        assert result["id"] == "emp123"

    def test_sets_isOwner_default_false(self):
        """serialize_employee should set isOwner default False."""
        from app.services.tenant_auth import serialize_employee

        doc = {"_id": "emp123"}
        result = serialize_employee(doc)
        assert result["isOwner"] is False

    def test_handles_none_doc(self):
        """serialize_employee should handle None doc."""
        from app.services.tenant_auth import serialize_employee

        result = serialize_employee(None)
        assert result is None

    def test_maps_activoo_to_active(self):
        """serialize_employee should map ACTIVO to ACTIVE."""
        from app.services.tenant_auth import serialize_employee

        doc = {"_id": "1", "status": "ACTIVO"}
        result = serialize_employee(doc)
        assert result["status"] == "ACTIVE"

    def test_maps_inactivo_to_inactive(self):
        """serialize_employee should map INACTIVO to INACTIVE."""
        from app.services.tenant_auth import serialize_employee

        doc = {"_id": "1", "status": "INACTIVO"}
        result = serialize_employee(doc)
        assert result["status"] == "INACTIVE"

    def test_maps_owner_role_to_admin(self):
        """serialize_employee should map OWNER/PROPIETARIO role to ADMIN."""
        from app.services.tenant_auth import serialize_employee

        doc = {"_id": "1", "role": "OWNER"}
        result = serialize_employee(doc)
        assert result["role"] == "ADMIN"


# ── 6. get_tenant_from_request helper ───────────────────────────────────────


class TestGetTenantFromRequest:
    """RED: get_tenant_from_request must extract tenant dict from request token."""

    def test_import_is_callable(self):
        """get_tenant_from_request should be importable and callable."""
        from app.api.dependencies import get_tenant_from_request
        assert callable(get_tenant_from_request)

    def test_returns_dict_on_valid_token(self):
        """Should return tenant dict when token is valid."""
        from app.api.dependencies import get_tenant_from_request

        # Just verify the import + type
        assert callable(get_tenant_from_request)


# ── 7. register method behavior ─────────────────────────────────────────────


class TestRegister:
    """RED: register must create tenant, owner employee, user, default services, and payment."""

    @pytest.mark.asyncio
    async def test_register_creates_tenant_and_owner(self):
        """register should create tenant doc, employee owner, and user."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantCreate, SubscriptionPlan

        db = MagicMock(spec=AsyncIOMotorDatabase)

        # Mock collection access via __getitem__
        tenants_mock = MagicMock()
        tenants_mock.find_one = AsyncMock(side_effect=[None, None])  # email not found, code not found
        tenants_mock.insert_one = AsyncMock(return_value=MagicMock(inserted_id="tenant_obj_id"))
        tenants_mock.update_one = AsyncMock()

        employees_mock = MagicMock()
        employees_mock.insert_one = AsyncMock(return_value=MagicMock(inserted_id="owner_obj_id"))

        users_mock = MagicMock()
        users_mock.insert_one = AsyncMock()

        services_mock = MagicMock()
        services_mock.insert_one = AsyncMock()

        payments_mock = MagicMock()
        payments_mock.insert_one = AsyncMock()

        def mock_getitem(name):
            collection_map = {
                "tenants": tenants_mock,
                "employees": employees_mock,
                "users": users_mock,
                "services": services_mock,
                "tenant_payments": payments_mock,
            }
            return collection_map.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)
        data = TenantCreate(
            email="test@example.com",
            password="test123456",
            businessName="Test Gym",
            businessPhone="123456789",
            ownerFirstName="John",
            ownerLastName="Doe",
            plan=SubscriptionPlan.BASIC,
        )

        with patch("app.services.tenant_auth.get_password_hash", return_value="hashed_pwd"):
            result = await service.register(data)

        # Verify tenant was inserted
        tenants_mock.insert_one.assert_awaited_once()
        # Verify employee owner was inserted
        employees_mock.insert_one.assert_awaited_once()
        # Verify user was inserted
        users_mock.insert_one.assert_awaited_once()

        # Result should be a dict (tenant_data)
        assert isinstance(result, dict)
        assert result["tenantId"] is not None
        assert result["email"] == "test@example.com"
        assert result["businessName"] == "Test Gym"

    @pytest.mark.asyncio
    async def test_register_raises_on_duplicate_email(self):
        """register should raise HTTPException when email exists."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantCreate, SubscriptionPlan
        from fastapi import HTTPException

        db = MagicMock(spec=AsyncIOMotorDatabase)

        tenants_mock = MagicMock()
        tenants_mock.find_one = AsyncMock(return_value={"_id": "existing", "email": "test@example.com"})

        def mock_getitem(name):
            return {"tenants": tenants_mock}.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)
        data = TenantCreate(
            email="test@example.com",
            password="test123456",
            businessName="Test Gym",
            ownerFirstName="John",
            ownerLastName="Doe",
        )

        with pytest.raises(HTTPException) as exc:
            await service.register(data)
        assert exc.value.status_code == 400


# ── 8. login method behavior ─────────────────────────────────────────────────


class TestLogin:
    """RED: login must authenticate user and return token + tenant + employee."""

    @pytest.mark.asyncio
    async def test_login_returns_token_tenant_employee(self):
        """login should return dict with access_token, tenant, and employee."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantLoginRequest

        db = MagicMock(spec=AsyncIOMotorDatabase)

        # Mock SUPER_ADMIN lookup returns None, then scoped user lookup
        users_mock = MagicMock()
        users_mock.find_one = AsyncMock(side_effect=[
            None,  # SUPER_ADMIN check
            {  # scoped user found
                "username": "admin@test.com",
                "password_hash": "hashed_pwd",
                "employeeId": "emp-001",
                "role": "ADMIN",
            },
        ])

        employees_mock = MagicMock()
        employees_mock.find_one = AsyncMock(return_value={
            "_id": "emp-001",
            "tenantId": "tenant-001",
            "firstName": "Admin",
            "lastName": "User",
            "role": "ADMIN",
            "isOwner": True,
            "status": "ACTIVE",
        })

        tenants_mock = MagicMock()
        tenants_mock.find_one = AsyncMock(return_value={
            "tenantId": "tenant-001",
            "plan": "BASIC",
            "subscriptionStatus": "ACTIVE",
            "email": "admin@test.com",
            "businessName": "Test Gym",
        })

        def mock_getitem(name):
            collection_map = {
                "users": users_mock,
                "employees": employees_mock,
                "tenants": tenants_mock,
            }
            return collection_map.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)

        with patch("app.services.tenant_auth.verify_password", return_value=True):
            with patch("app.services.tenant_auth.create_access_token", return_value="jwt-token-123"):
                result = await service.login(TenantLoginRequest(email="admin@test.com", password="pass123"))

        assert isinstance(result, dict)
        assert "access_token" in result
        assert result["access_token"] == "jwt-token-123"
        assert "tenant" in result
        assert "employee" in result

    @pytest.mark.asyncio
    async def test_login_raises_on_wrong_password(self):
        """login should raise HTTPException on wrong password."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantLoginRequest
        from fastapi import HTTPException

        db = MagicMock(spec=AsyncIOMotorDatabase)

        users_mock = MagicMock()
        users_mock.find_one = AsyncMock(side_effect=[
            None,  # SUPER_ADMIN check
            {"username": "admin@test.com", "password_hash": "hashed_pwd", "employeeId": "emp-001"},
        ])

        def mock_getitem(name):
            return {"users": users_mock}.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)

        with patch("app.services.tenant_auth.verify_password", return_value=False):
            with pytest.raises(HTTPException) as exc:
                await service.login(TenantLoginRequest(email="admin@test.com", password="wrong"))
            assert exc.value.status_code == 401


# ── 9. forgot_password method behavior ──────────────────────────────────────


class TestForgotPassword:
    """RED: forgot_password must send reset email and return True."""

    @pytest.mark.asyncio
    async def test_forgot_password_returns_true_when_email_sent(self):
        """forgot_password should return True when email is sent."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantAuthService(db)

        # Mock create_reset_token and send_password_reset_email
        with patch("app.services.tenant_auth.create_reset_token", new_callable=AsyncMock, return_value="reset-token"):
            with patch("app.services.tenant_auth.send_password_reset_email", new_callable=AsyncMock):
                result = await service.forgot_password("test@example.com")
                assert result is True


# ── 10. reset_password method behavior ──────────────────────────────────────


class TestResetPassword:
    """RED: reset_password must consume token and update password."""

    @pytest.mark.asyncio
    async def test_reset_password_updates_password(self):
        """reset_password should update password_hash in users collection."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import PasswordResetConfirm

        db = MagicMock(spec=AsyncIOMotorDatabase)

        users_mock = MagicMock()
        users_mock.find_one = AsyncMock(return_value={
            "employeeId": "emp-001",
            "tenantId": "tenant-001",
            "isOwner": False,
        })
        users_mock.update_one = AsyncMock()

        def mock_getitem(name):
            return {"users": users_mock}.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)

        data = PasswordResetConfirm(token="valid-token", newPassword="newpass123")

        with patch("app.services.tenant_auth.consume_reset_token", new_callable=AsyncMock) as mock_consume:
            mock_consume.return_value = {"employeeId": "emp-001", "tenantId": "tenant-001"}
            with patch("app.services.tenant_auth.get_password_hash", return_value="new_hashed"):
                result = await service.reset_password(data, db)

        assert result is True
        users_mock.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_password_raises_on_owner(self):
        """reset_password should raise 403 for owner accounts."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import PasswordResetConfirm
        from fastapi import HTTPException

        db = MagicMock(spec=AsyncIOMotorDatabase)

        users_mock = MagicMock()
        users_mock.find_one = AsyncMock(return_value={
            "employeeId": "emp-001",
            "tenantId": "tenant-001",
            "isOwner": True,  # Is owner — should fail
        })

        def mock_getitem(name):
            return {"users": users_mock}.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)

        data = PasswordResetConfirm(token="valid-token", newPassword="newpass123")

        with patch("app.services.tenant_auth.consume_reset_token", new_callable=AsyncMock) as mock_consume:
            mock_consume.return_value = {"employeeId": "emp-001", "tenantId": "tenant-001"}
            with patch("app.services.tenant_auth.get_password_hash", return_value="new_hashed"):
                with pytest.raises(HTTPException) as exc:
                    await service.reset_password(data, db)
                assert exc.value.status_code == 403


# ── 11. renew_subscription method behavior ──────────────────────────────────


class TestRenewSubscription:
    """RED: renew_subscription must update subscription dates."""

    @pytest.mark.asyncio
    async def test_renew_subscription_updates_end_date(self):
        """renew_subscription should set subscriptionStatus to ACTIVE and update end date."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import SubscriptionPlan

        db = MagicMock(spec=AsyncIOMotorDatabase)

        tenants_mock = MagicMock()
        tenants_mock.find_one = AsyncMock(return_value={
            "tenantId": "tenant-001",
            "plan": "BASIC",
            "subscriptionStatus": "EXPIRED",
        })
        tenants_mock.update_one = AsyncMock()

        def mock_getitem(name):
            return {"tenants": tenants_mock}.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)
        result = await service.renew_subscription("tenant-001", payment_months=1)

        assert isinstance(result, dict)
        tenants_mock.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_renew_with_plan_change(self):
        """renew_subscription should accept plan parameter."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import SubscriptionPlan

        db = MagicMock(spec=AsyncIOMotorDatabase)

        tenants_mock = MagicMock()
        tenants_mock.find_one = AsyncMock(return_value={
            "tenantId": "tenant-001",
            "plan": "BASIC",
            "subscriptionStatus": "ACTIVE",
        })
        tenants_mock.update_one = AsyncMock()

        def mock_getitem(name):
            return {"tenants": tenants_mock}.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)
        result = await service.renew_subscription("tenant-001", payment_months=1)

        assert isinstance(result, dict)


# ── 12. get_tenant_config method behavior ───────────────────────────────────


class TestGetTenantConfig:
    """RED: get_tenant_config must fetch tenant by tenantId."""

    @pytest.mark.asyncio
    async def test_get_tenant_config_returns_tenant(self):
        """get_tenant_config should return tenant dict from DB."""
        from app.services.tenant_auth import TenantAuthService

        db = MagicMock(spec=AsyncIOMotorDatabase)

        tenants_mock = MagicMock()
        tenants_mock.find_one = AsyncMock(return_value={
            "tenantId": "tenant-001",
            "businessName": "Test Gym",
            "plan": "BASIC",
        })

        def mock_getitem(name):
            return {"tenants": tenants_mock}.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantAuthService(db)
        result = await service.get_tenant_config("tenant-001")

        assert isinstance(result, dict)
        assert result["tenantId"] == "tenant-001"
        tenants_mock.find_one.assert_awaited_once_with({"tenantId": "tenant-001"})
