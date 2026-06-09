"""Tests for app/services/tenant_demo.py — TenantDemoService extraction.

These tests verify:
1. Module/service imports correctly
2. TenantDemoService class structure (constructor, expected methods)
3. Backward-compatible wrapper function exists
4. Service methods delegate to self.db correctly
5. cleanup method calls delete_many with correct filters
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, call
from motor.motor_asyncio import AsyncIOMotorDatabase


# ── 1. Module imports ─────────────────────────────────────────────────────


class TestModuleImports:
    """RED: Verify the module is importable and exposes expected names."""

    def test_module_can_be_imported(self):
        """Module should be importable."""
        import app.services.tenant_demo
        assert app.services.tenant_demo is not None

    def test_tenant_demo_service_class_exists(self):
        """TenantDemoService class should be exposed."""
        from app.services.tenant_demo import TenantDemoService
        assert TenantDemoService is not None

    def test_initialize_tenant_demo_wrapper_exists(self):
        """Backward-compatible wrapper function should be exposed."""
        from app.services.tenant_demo import initialize_tenant_demo
        assert callable(initialize_tenant_demo)


# ── 2. Class instantiation ────────────────────────────────────────────────


class TestTenantDemoServiceInstantiation:
    """RED: TenantDemoService must accept db in constructor."""

    def test_constructor_accepts_db(self):
        """Constructor should accept an AsyncIOMotorDatabase instance."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert service.db is db

    def test_constructor_stores_db(self):
        """Constructor should store db as self.db."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert hasattr(service, 'db')


# ── 3. Method signatures ──────────────────────────────────────────────────


class TestTenantDemoServiceMethods:
    """RED: Verify all expected methods exist with correct signatures."""

    def test_initialize_method_exists(self):
        """initialize() should be an async method."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert hasattr(service, 'initialize')
        assert callable(service.initialize)

    def test_seed_data_method_exists(self):
        """seed_data() should be an async method."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert hasattr(service, 'seed_data')
        assert callable(service.seed_data)

    def test_seed_attendance_method_exists(self):
        """seed_attendance() should be an async method."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert hasattr(service, 'seed_attendance')
        assert callable(service.seed_attendance)

    def test_seed_owner_method_exists(self):
        """seed_owner() should be an async method."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert hasattr(service, 'seed_owner')
        assert callable(service.seed_owner)

    def test_create_default_services_method_exists(self):
        """create_default_services() should be an async method."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert hasattr(service, 'create_default_services')
        assert callable(service.create_default_services)

    def test_cleanup_method_exists(self):
        """cleanup() should be an async method."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = TenantDemoService(db)
        assert hasattr(service, 'cleanup')
        assert callable(service.cleanup)


# ── 4. cleanup method behavior ────────────────────────────────────────────


class TestCleanup:
    """RED: cleanup must delete non-seed data for a given tenant_id."""

    @pytest.mark.asyncio
    async def test_cleanup_calls_delete_many_on_all_collections(self):
        """cleanup should call delete_many on each demo collection."""
        from app.services.tenant_demo import TenantDemoService
        from app.database import Collections

        # Setup: mock db with all collections returning AsyncMock
        db = MagicMock(spec=AsyncIOMotorDatabase)
        # Make each collection access return an AsyncMock for delete_many
        for col_name in [
            Collections.SALES, Collections.CLIENTS, Collections.INVOICES,
            Collections.PRODUCTS, Collections.ATTENDANCE, Collections.SERVICES,
            Collections.EMPLOYEES, Collections.NOTIFICATION_CONFIGS,
            Collections.NOTIFICATION_LOGS, Collections.FINGERPRINTS,
        ]:
            col_mock = MagicMock()
            col_mock.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
            getattr(db, col_name) if hasattr(db, col_name) else None
            # Use __getitem__ since db[collection_name] is used for dict access
            # But motor uses attribute access: db.collection_name
            # Actually in the code it's db[collection_name] - subscript access
            # So we need __getitem__ to return a mock
            pass

        # For motor, db["collection_name"] uses __getitem__
        # We need the mock to support subscript access
        collection_mocks = {}
        for col_name in [
            Collections.SALES, Collections.CLIENTS, Collections.INVOICES,
            Collections.PRODUCTS, Collections.ATTENDANCE, Collections.SERVICES,
            Collections.EMPLOYEES, Collections.NOTIFICATION_CONFIGS,
            Collections.NOTIFICATION_LOGS, Collections.FINGERPRINTS, "users",
        ]:
            col_mock = MagicMock()
            col_mock.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))
            collection_mocks[col_name] = col_mock

        def mock_getitem(name):
            return collection_mocks.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantDemoService(db)
        tenant_id = "test-demo-001"
        result = await service.cleanup(tenant_id)

        # Verify delete_many was called on each collection with correct filter
        expected_filter = {"tenantId": tenant_id, "isSeed": {"$ne": True}}
        for col_name in [
            Collections.SALES, Collections.CLIENTS, Collections.INVOICES,
            Collections.PRODUCTS, Collections.ATTENDANCE, Collections.SERVICES,
            Collections.EMPLOYEES, Collections.NOTIFICATION_CONFIGS,
            Collections.NOTIFICATION_LOGS, Collections.FINGERPRINTS,
        ]:
            collection_mocks[col_name].delete_many.assert_awaited_once_with(expected_filter)

        # Verify users collection too
        collection_mocks["users"].delete_many.assert_awaited_once_with(expected_filter)

        # Verify the return dict has entries for all collections
        assert "message" in result
        assert "deleted" in result
        assert "tenantId" in result

    @pytest.mark.asyncio
    async def test_cleanup_includes_all_collections(self):
        """cleanup should include all expected demo collections."""
        from app.services.tenant_demo import TenantDemoService
        from app.database import Collections

        db = MagicMock(spec=AsyncIOMotorDatabase)
        collection_mocks = {}
        expected_collections = [
            Collections.SALES, Collections.CLIENTS, Collections.INVOICES,
            Collections.PRODUCTS, Collections.ATTENDANCE, Collections.SERVICES,
            Collections.EMPLOYEES, Collections.NOTIFICATION_CONFIGS,
            Collections.NOTIFICATION_LOGS, Collections.FINGERPRINTS,
        ]
        for col_name in expected_collections + ["users"]:
            col_mock = MagicMock()
            col_mock.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
            collection_mocks[col_name] = col_mock

        def mock_getitem(name):
            return collection_mocks.get(name, MagicMock())

        db.__getitem__.side_effect = mock_getitem

        service = TenantDemoService(db)
        result = await service.cleanup("tenant-001")

        # deleted dict should have entries for all collections + users
        assert len(result["deleted"]) == len(expected_collections) + 1

    @pytest.mark.asyncio
    async def test_cleanup_only_removes_non_seed_data(self):
        """cleanup should filter with isSeed: {$ne: True}, not delete seed."""
        from app.services.tenant_demo import TenantDemoService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        sales_mock = MagicMock()
        sales_mock.delete_many = AsyncMock(return_value=MagicMock(deleted_count=5))
        db.__getitem__.return_value = sales_mock

        service = TenantDemoService(db)
        await service.cleanup("demo-tenant")

        # Verify the isSeed filter is used
        call_args = sales_mock.delete_many.call_args[0][0]
        assert call_args["isSeed"] == {"$ne": True}
