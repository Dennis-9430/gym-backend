"""Tests for app/services/admin_payment.py — AdminPaymentService extraction.

Covers: constructor, method signatures, and key behaviors.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from motor.motor_asyncio import AsyncIOMotorDatabase


@pytest.fixture(autouse=True)
def clean_test_db():
    """Override conftest autouse fixture — unit tests mock db, no MongoDB needed."""
    pass


class TestAdminPaymentServiceModule:
    """RED: Verify the module is importable and exposes expected names."""

    def test_module_can_be_imported(self):
        import app.services.admin_payment
        assert app.services.admin_payment is not None

    def test_admin_payment_service_class_exists(self):
        from app.services.admin_payment import AdminPaymentService
        assert AdminPaymentService is not None


class TestAdminPaymentServiceInstantiation:
    """RED: AdminPaymentService must accept db in constructor."""

    def test_constructor_accepts_db(self):
        from app.services.admin_payment import AdminPaymentService
        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = AdminPaymentService(db)
        assert service.db is db


class TestAdminPaymentServiceMethods:
    """RED: Verify all expected methods exist."""

    def setup_service(self):
        from app.services.admin_payment import AdminPaymentService
        db = MagicMock(spec=AsyncIOMotorDatabase)
        return AdminPaymentService(db)

    def test_manual_payment_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'manual_payment')
        assert callable(service.manual_payment)

    def test_list_payments_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'list_payments')
        assert callable(service.list_payments)

    def test_list_pending_payments_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'list_pending_payments')
        assert callable(service.list_pending_payments)

    def test_approve_payment_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'approve_payment')
        assert callable(service.approve_payment)

    def test_reject_payment_method_exists(self):
        service = self.setup_service()
        assert hasattr(service, 'reject_payment')
        assert callable(service.reject_payment)


class TestAdminPaymentServiceBehavior:
    """GREEN: Verify methods delegate to self.db correctly."""

    @pytest.mark.asyncio
    async def test_list_payments_returns_paginated(self):
        from app.services.admin_payment import AdminPaymentService
        from app.database import Collections

        db = MagicMock(spec=AsyncIOMotorDatabase)
        tenants_col = MagicMock()
        tenants_col.find_one = AsyncMock(return_value={
            "_id": "abc", "tenantId": "t-001"
        })

        payments_col = MagicMock()
        payments_col.count_documents = AsyncMock(return_value=5)
        find_cursor = MagicMock()
        find_cursor.to_list = AsyncMock(return_value=[
            {"_id": "pay1", "tenantId": "t-001", "amount": 50.0}
        ])
        payments_col.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=find_cursor)
                ))
            ))
        ))

        collection_map = {Collections.TENANTS: tenants_col, Collections.TENANT_PAYMENTS: payments_col}

        def mock_getitem(name):
            return collection_map[name]

        db.__getitem__.side_effect = mock_getitem

        service = AdminPaymentService(db)
        result = await service.list_payments("t-001", 1, 20)

        assert result["total"] == 5
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "pay1"

    @pytest.mark.asyncio
    async def test_list_pending_payments_filters_transfer_pending(self):
        from app.services.admin_payment import AdminPaymentService
        from app.database import Collections

        db = MagicMock(spec=AsyncIOMotorDatabase)
        payments_col = MagicMock()
        payments_col.count_documents = AsyncMock(return_value=3)

        # Mock to_list returning cursor items
        find_cursor = MagicMock()
        find_cursor.to_list = AsyncMock(return_value=[
            {"_id": "p1", "tenantId": "t-001", "method": "TRANSFER", "status": "PENDING"}
        ])

        payments_col.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=find_cursor)
                ))
            ))
        ))

        tenants_col = MagicMock()
        tenants_col.find = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[
                {"tenantId": "t-001", "businessName": "Test", "email": "test@test.com", "businessCode": "tt"}
            ])
        ))

        collection_map = {Collections.TENANT_PAYMENTS: payments_col, Collections.TENANTS: tenants_col}

        def mock_getitem(name):
            return collection_map[name]

        db.__getitem__.side_effect = mock_getitem

        service = AdminPaymentService(db)
        result = await service.list_pending_payments(1, 20)

        assert result["total"] == 3
        assert len(result["items"]) == 1
        assert result["items"][0]["tenantName"] == "Test"
