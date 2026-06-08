"""Tests for app/services/admin_tenant.py — AdminTenantService extraction.

Covers: constructor, method signatures, and key behaviors.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from motor.motor_asyncio import AsyncIOMotorDatabase


@pytest.fixture(autouse=True)
def clean_test_db():
    """Override conftest autouse fixture — unit tests mock db, no MongoDB needed."""
    pass


class TestAdminTenantServiceModule:
    """RED: Verify the module is importable and exposes expected names."""

    def test_module_can_be_imported(self):
        import app.services.admin_tenant
        assert app.services.admin_tenant is not None

    def test_admin_tenant_service_class_exists(self):
        from app.services.admin_tenant import AdminTenantService
        assert AdminTenantService is not None


class TestAdminTenantServiceInstantiation:
    """RED: AdminTenantService must accept db in constructor."""

    def test_constructor_accepts_db(self):
        from app.services.admin_tenant import AdminTenantService
        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = AdminTenantService(db)
        assert service.db is db


class TestAdminTenantServiceMethods:
    """RED: Verify all expected methods exist."""

    def setup_service(self):
        from app.services.admin_tenant import AdminTenantService
        db = MagicMock(spec=AsyncIOMotorDatabase)
        return AdminTenantService(db)

    def test_get_dashboard_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'get_dashboard')
        assert callable(service.get_dashboard)

    def test_list_tenants_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'list_tenants')
        assert callable(service.list_tenants)

    def test_get_tenant_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'get_tenant')
        assert callable(service.get_tenant)

    def test_suspend_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'suspend')
        assert callable(service.suspend)

    def test_cancel_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'cancel')
        assert callable(service.cancel)

    def test_reactivate_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'reactivate')
        assert callable(service.reactivate)

    def test_toggle_biometric_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'toggle_biometric')
        assert callable(service.toggle_biometric)

    def test_delete_tenant_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'delete_tenant')
        assert callable(service.delete_tenant)


class TestAdminTenantServiceBehavior:
    """GREEN: Verify methods delegate to self.db correctly."""

    @pytest.mark.asyncio
    async def test_get_dashboard_counts_documents(self):
        from app.services.admin_tenant import AdminTenantService
        from app.database import Collections
        from app.models.tenant import SubscriptionStatus

        db = MagicMock(spec=AsyncIOMotorDatabase)
        # Mock count_documents for each status
        col_mock = MagicMock()
        col_mock.count_documents = AsyncMock(return_value=1)

        def mock_getitem(name):
            return col_mock

        db.__getitem__.side_effect = mock_getitem

        # Mock aggregate for revenue — aggregate() sync returns cursor, to_list() is async
        agg_cursor = MagicMock()
        agg_cursor.to_list = AsyncMock(return_value=[{"total": 100.0}])
        col_mock.aggregate = MagicMock(return_value=agg_cursor)

        # Mock find for recent payments
        find_cursor = MagicMock()
        find_cursor.to_list = AsyncMock(return_value=[])
        col_mock.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                limit=MagicMock(return_value=find_cursor)
            ))
        ))

        service = AdminTenantService(db)
        result = await service.get_dashboard()

        assert result["total_tenants"] == 1
        assert "active" in result
        assert "monthly_revenue" in result
        assert result["monthly_revenue"] == 100.0
        assert col_mock.count_documents.await_count >= 1

    @pytest.mark.asyncio
    async def test_list_tenants_returns_paginated(self):
        from app.services.admin_tenant import AdminTenantService
        from app.database import Collections

        db = MagicMock(spec=AsyncIOMotorDatabase)
        col_mock = MagicMock()
        col_mock.count_documents = AsyncMock(return_value=10)
        find_cursor = MagicMock()
        find_cursor.to_list = AsyncMock(return_value=[
            {"_id": "abc123", "tenantId": "t-001", "businessName": "Test"}
        ])
        col_mock.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=find_cursor)
                ))
            ))
        ))

        def mock_getitem(name):
            return col_mock

        db.__getitem__.side_effect = mock_getitem

        service = AdminTenantService(db)
        result = await service.list_tenants(None, None, None, 1, 20)

        assert result["total"] == 10
        assert len(result["items"]) == 1
        assert result["page"] == 1
        assert result["limit"] == 20
        assert result["items"][0]["id"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_tenant_found(self):
        from app.services.admin_tenant import AdminTenantService
        from app.database import Collections

        db = MagicMock(spec=AsyncIOMotorDatabase)
        col_mock = MagicMock()
        col_mock.find_one = AsyncMock(return_value={
            "_id": "abc123", "tenantId": "t-001", "businessName": "Test"
        })
        agg_cursor = MagicMock()
        agg_cursor.to_list = AsyncMock(return_value=[
            {"total_paid": 500.0, "last_payment_date": "2026-01-01"}
        ])
        col_mock.aggregate = MagicMock(return_value=agg_cursor)  # sync, not awaitable

        def mock_getitem(name):
            return col_mock

        db.__getitem__.side_effect = mock_getitem

        service = AdminTenantService(db)
        result = await service.get_tenant("t-001")

        assert result["tenantId"] == "t-001"
        assert result["id"] == "abc123"
        assert result["total_paid"] == 500.0

    @pytest.mark.asyncio
    async def test_suspend_updates_status(self):
        from app.services.admin_tenant import AdminTenantService
        from app.models.tenant import SubscriptionStatus

        db = MagicMock(spec=AsyncIOMotorDatabase)
        col_mock = MagicMock()
        col_mock.find_one = AsyncMock(side_effect=[
            {"_id": "abc", "tenantId": "t-001", "subscriptionStatus": SubscriptionStatus.ACTIVE},
            {"_id": "abc", "tenantId": "t-001", "subscriptionStatus": SubscriptionStatus.SUSPENDED},
        ])
        col_mock.update_one = AsyncMock()

        def mock_getitem(name):
            return col_mock
        db.__getitem__.side_effect = mock_getitem

        service = AdminTenantService(db)
        result = await service.suspend("t-001", "Morosidad")

        assert result["subscriptionStatus"] == SubscriptionStatus.SUSPENDED
        col_mock.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_tenant_removes_data(self):
        from app.services.admin_tenant import AdminTenantService
        from app.database import Collections

        db = MagicMock(spec=AsyncIOMotorDatabase)
        col_mock = MagicMock()
        col_mock.find_one = AsyncMock(return_value={
            "_id": "abc", "tenantId": "t-001", "businessName": "Test Gym"
        })

        # delete_many and delete_one ARE awaitable in Motor
        delete_result = MagicMock()
        delete_result.deleted_count = 5

        col_mock.delete_many = AsyncMock(return_value=delete_result)
        col_mock.delete_one = AsyncMock(return_value=delete_result)

        def mock_getitem(name):
            return col_mock

        db.__getitem__.side_effect = mock_getitem

        service = AdminTenantService(db)
        result = await service.delete_tenant("t-001")

        assert "message" in result
        assert "deleted" in result
        assert "Test Gym" in result["message"]
