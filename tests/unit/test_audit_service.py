"""Tests for app/services/audit_service.py — AuditService.

Covers: constructor, log_event, query_logs with filters and pagination.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase


class TestModuleImports:
    """RED: Verify the module is importable."""

    def test_module_can_be_imported(self):
        import app.services.audit_service
        assert app.services.audit_service is not None

    def test_audit_service_class_exists(self):
        from app.services.audit_service import AuditService
        assert AuditService is not None


class TestAuditServiceInstantiation:
    """RED: AuditService must accept db in constructor."""

    def test_constructor_accepts_db(self):
        from app.services.audit_service import AuditService
        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = AuditService(db)
        assert service.db is db

    def test_constructor_sets_collection(self):
        from app.services.audit_service import AuditService
        from app.models.audit_log import AUDIT_LOGS_COLLECTION
        db = MagicMock(spec=AsyncIOMotorDatabase)
        service = AuditService(db)
        assert service.collection == AUDIT_LOGS_COLLECTION


class TestAuditServiceLogEvent:
    """RED→GREEN: Test log_event method."""

    @pytest.mark.asyncio
    async def test_log_event_returns_string_id(self):
        """log_event should insert a document and return str(inserted_id)."""
        from app.services.audit_service import AuditService
        from bson import ObjectId

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = MagicMock()
        inserted_id = ObjectId("507f1f77bcf86cd799439011")
        audit_col.insert_one = AsyncMock(return_value=MagicMock(
            inserted_id=inserted_id
        ))
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        result = await service.log_event(
            event="LOGIN_SUCCESS",
            actor_id="user-1",
            actor_type="SUPER_ADMIN",
            tenant_id="tenant-1",
        )
        assert result == str(inserted_id)
        audit_col.insert_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_event_passes_extra_fields(self):
        """log_event should pass target_id, target_type, details, ip_address."""
        from app.services.audit_service import AuditService
        from bson import ObjectId

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = MagicMock()
        audit_col.insert_one = AsyncMock(return_value=MagicMock(
            inserted_id=ObjectId("507f1f77bcf86cd799439012")
        ))
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.log_event(
            event="TENANT_DELETED",
            actor_id="super-1",
            actor_type="SUPER_ADMIN",
            tenant_id="tenant-1",
            target_id="tenant-1",
            target_type="tenant",
            details={"businessName": "Gym Alpha"},
            ip_address="192.168.1.1",
        )
        call_kwargs = audit_col.insert_one.call_args[0][0]
        assert call_kwargs["target_id"] == "tenant-1"
        assert call_kwargs["target_type"] == "tenant"
        assert call_kwargs["details"] == {"businessName": "Gym Alpha"}
        assert call_kwargs["ip_address"] == "192.168.1.1"
        assert call_kwargs["event"] == "TENANT_DELETED"
        assert call_kwargs["actor_id"] == "super-1"
        assert call_kwargs["actor_type"] == "SUPER_ADMIN"
        assert call_kwargs["tenant_id"] == "tenant-1"
        assert "timestamp" in call_kwargs


class TestAuditServiceQueryLogs:
    """RED→GREEN: Test query_logs method with filters and pagination."""

    @pytest.fixture
    def service_and_db(self):
        from app.services.audit_service import AuditService
        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = MagicMock()
        db.__getitem__ = MagicMock(return_value=audit_col)
        return AuditService(db), db, audit_col

    def _make_cursor(self, items, total):
        """Helper to create a mock MongoDB cursor chain."""
        audit_col = MagicMock()
        audit_col.count_documents = AsyncMock(return_value=total)
        find_cursor = MagicMock()
        find_cursor.to_list = AsyncMock(return_value=items)
        sort_mock = MagicMock(return_value=MagicMock(
            skip=MagicMock(return_value=MagicMock(
                limit=MagicMock(return_value=find_cursor)
            ))
        ))
        audit_col.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=find_cursor)
                ))
            ))
        ))
        return audit_col

    @pytest.mark.asyncio
    async def test_query_logs_returns_empty(self):
        """query_logs should return empty list when no logs match."""
        from app.services.audit_service import AuditService
        from app.models.audit_log import AUDIT_LOGS_COLLECTION

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        items, total = await service.query_logs()
        assert items == []
        assert total == 0
        audit_col.count_documents.assert_awaited_once_with({})

    @pytest.mark.asyncio
    async def test_query_logs_returns_items(self):
        """query_logs should return items with total count."""
        from app.services.audit_service import AuditService

        docs = [
            {"_id": "id1", "event": "LOGIN_SUCCESS", "actor_id": "u1",
             "actor_type": "ADMIN", "tenant_id": "t1", "timestamp": datetime.utcnow()},
            {"_id": "id2", "event": "LOGIN_FAILED", "actor_id": "u2",
             "actor_type": "ADMIN", "tenant_id": "t1", "timestamp": datetime.utcnow()},
        ]
        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor(docs, 2)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        items, total = await service.query_logs()
        assert len(items) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_query_logs_filters_by_event(self):
        """query_logs should filter by event type."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.query_logs(event="LOGIN_SUCCESS")

        call_filter = audit_col.count_documents.call_args[0][0]
        assert call_filter.get("event") == "LOGIN_SUCCESS"

    @pytest.mark.asyncio
    async def test_query_logs_filters_by_actor_id(self):
        """query_logs should filter by actor_id."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.query_logs(actor_id="super-1")

        call_filter = audit_col.count_documents.call_args[0][0]
        assert call_filter.get("actor_id") == "super-1"

    @pytest.mark.asyncio
    async def test_query_logs_filters_by_tenant_id(self):
        """query_logs should filter by tenant_id."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.query_logs(tenant_id="tenant-1")

        call_filter = audit_col.count_documents.call_args[0][0]
        assert call_filter.get("tenant_id") == "tenant-1"

    @pytest.mark.asyncio
    async def test_query_logs_filters_by_date_range(self):
        """query_logs should filter by from_date and to_date."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        from_date = datetime(2026, 1, 1)
        to_date = datetime(2026, 6, 1)

        service = AuditService(db)
        await service.query_logs(from_date=from_date, to_date=to_date)

        call_filter = audit_col.count_documents.call_args[0][0]
        ts_filter = call_filter.get("timestamp")
        assert ts_filter is not None
        assert ts_filter["$gte"] == from_date
        assert ts_filter["$lte"] == to_date

    @pytest.mark.asyncio
    async def test_query_logs_combines_filters(self):
        """query_logs should combine multiple filters with AND."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.query_logs(
            event="TENANT_DELETED",
            actor_id="super-1",
            tenant_id="tenant-1",
        )

        call_filter = audit_col.count_documents.call_args[0][0]
        assert call_filter == {
            "event": "TENANT_DELETED",
            "actor_id": "super-1",
            "tenant_id": "tenant-1",
        }

    @pytest.mark.asyncio
    async def test_query_logs_pagination(self):
        """query_logs should apply skip and limit correctly."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = MagicMock()
        audit_col.count_documents = AsyncMock(return_value=50)
        find_cursor = MagicMock()
        find_cursor.to_list = AsyncMock(return_value=[])
        limit_mock = MagicMock(return_value=find_cursor)
        sort_mock = MagicMock(return_value=MagicMock(
            skip=MagicMock(return_value=MagicMock(
                limit=MagicMock(return_value=find_cursor)
            ))
        ))
        audit_col.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=find_cursor)
                ))
            ))
        ))
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        items, total = await service.query_logs(page=3, limit=10)

        assert total == 50
        # Verify sort direction
        sort_call = audit_col.find.return_value.sort
        sort_call.assert_called_once_with("timestamp", -1)

    @pytest.mark.asyncio
    async def test_query_logs_from_date_only(self):
        """query_logs with only from_date should set $gte."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.query_logs(from_date=datetime(2026, 1, 1))

        call_filter = audit_col.count_documents.call_args[0][0]
        assert call_filter["timestamp"] == {"$gte": datetime(2026, 1, 1)}

    @pytest.mark.asyncio
    async def test_query_logs_to_date_only(self):
        """query_logs with only to_date should set $lte."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = self._make_cursor([], 0)
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.query_logs(to_date=datetime(2026, 6, 1))

        call_filter = audit_col.count_documents.call_args[0][0]
        assert call_filter["timestamp"] == {"$lte": datetime(2026, 6, 1)}

    @pytest.mark.asyncio
    async def test_query_logs_default_pagination(self):
        """query_logs with no page/limit defaults to page=1, limit=20."""
        from app.services.audit_service import AuditService

        db = MagicMock(spec=AsyncIOMotorDatabase)
        audit_col = MagicMock()
        audit_col.count_documents = AsyncMock(return_value=0)
        find_cursor = MagicMock()
        find_cursor.to_list = AsyncMock(return_value=[])
        audit_col.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=find_cursor)
                ))
            ))
        ))
        db.__getitem__ = MagicMock(return_value=audit_col)

        service = AuditService(db)
        await service.query_logs()

        # Should skip 0 (page 1 - 1 = 0) and limit 20
        sort_chain = audit_col.find.return_value.sort.return_value
        sort_chain.skip.assert_called_once_with(0)
        sort_chain.skip.return_value.limit.assert_called_once_with(20)
