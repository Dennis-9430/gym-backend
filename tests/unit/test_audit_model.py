"""Tests for app/models/audit_log.py — AuditLog model and AuditEvents constants.

These tests verify:
1. AuditLog model structure and field types
2. AuditEvents constants class
3. AUDIT_LOGS_COLLECTION constant
"""
import pytest
from datetime import datetime


class TestModuleImports:
    """RED: Verify the module is importable and exposes expected names."""

    def test_module_can_be_imported(self):
        """Module should be importable."""
        import app.models.audit_log
        assert app.models.audit_log is not None

    def test_audit_log_class_exists(self):
        """AuditLog class should be exposed."""
        from app.models.audit_log import AuditLog
        assert AuditLog is not None

    def test_audit_events_class_exists(self):
        """AuditEvents class should be exposed."""
        from app.models.audit_log import AuditEvents
        assert AuditEvents is not None

    def test_collection_constant_exists(self):
        """AUDIT_LOGS_COLLECTION constant should be exposed."""
        from app.models.audit_log import AUDIT_LOGS_COLLECTION
        assert AUDIT_LOGS_COLLECTION == "audit_logs"


class TestAuditLogModel:
    """RED: Verify AuditLog Pydantic model fields."""

    def setup_method(self):
        from app.models.audit_log import AuditLog, AuditEvents
        self.AuditLog = AuditLog
        self.AuditEvents = AuditEvents

    def test_required_fields(self):
        """AuditLog requires event, actor_id, actor_type, tenant_id."""
        log = self.AuditLog(
            event=self.AuditEvents.LOGIN_SUCCESS,
            actor_id="user-1",
            actor_type="SUPER_ADMIN",
            tenant_id="tenant-1",
        )
        assert log.event == self.AuditEvents.LOGIN_SUCCESS
        assert log.actor_id == "user-1"
        assert log.actor_type == "SUPER_ADMIN"
        assert log.tenant_id == "tenant-1"

    def test_optional_fields_default_to_none(self):
        """AuditLog optional fields default correctly."""
        log = self.AuditLog(
            event="TEST_EVENT",
            actor_id="user-1",
            actor_type="ADMIN",
            tenant_id="tenant-1",
        )
        assert log.target_id is None
        assert log.target_type is None
        assert log.details == {}
        assert log.ip_address is None

    def test_timestamp_defaults_to_utcnow(self):
        """AuditLog timestamp defaults to a datetime (approximately now)."""
        from app.models.audit_log import AuditLog
        log = AuditLog(
            event="TEST_EVENT",
            actor_id="user-1",
            actor_type="ADMIN",
            tenant_id="tenant-1",
        )
        assert isinstance(log.timestamp, datetime)
        # Should be very recent
        now = datetime.utcnow()
        diff = abs((now - log.timestamp).total_seconds())
        assert diff < 5, f"Timestamp too far from now: {diff}s"

    def test_all_fields_populated(self):
        """AuditLog with all fields populated serializes correctly."""
        from datetime import datetime
        from app.models.audit_log import AuditLog

        ts = datetime(2026, 6, 9, 12, 0, 0)
        log = AuditLog(
            event="TENANT_DELETED",
            actor_id="super-1",
            actor_type="SUPER_ADMIN",
            tenant_id="tenant-1",
            target_id="tenant-1",
            target_type="tenant",
            details={"businessName": "Gym Alpha", "reason": "Fraud"},
            ip_address="192.168.1.1",
            timestamp=ts,
        )
        dumped = log.model_dump()
        assert dumped["event"] == "TENANT_DELETED"
        assert dumped["actor_id"] == "super-1"
        assert dumped["actor_type"] == "SUPER_ADMIN"
        assert dumped["tenant_id"] == "tenant-1"
        assert dumped["target_id"] == "tenant-1"
        assert dumped["target_type"] == "tenant"
        assert dumped["details"] == {"businessName": "Gym Alpha", "reason": "Fraud"}
        assert dumped["ip_address"] == "192.168.1.1"
        assert dumped["timestamp"] == ts

    def test_details_accepts_nested_dict(self):
        """AuditLog details field accepts complex nested dicts."""
        from app.models.audit_log import AuditLog

        log = AuditLog(
            event="PAYMENT_APPROVED",
            actor_id="super-1",
            actor_type="SUPER_ADMIN",
            tenant_id="tenant-1",
            details={"payment": {"id": "pay-1", "amount": 150.0, "method": "TRANSFER"}},
        )
        assert log.details["payment"]["amount"] == 150.0


class TestAuditEvents:
    """RED: Verify AuditEvents constants class."""

    def test_login_events_exist(self):
        """Login-related events are defined."""
        from app.models.audit_log import AuditEvents
        assert AuditEvents.LOGIN_SUCCESS == "LOGIN_SUCCESS"
        assert AuditEvents.LOGIN_FAILED == "LOGIN_FAILED"
        assert AuditEvents.FORGOT_PASSWORD == "FORGOT_PASSWORD"
        assert AuditEvents.RESET_PASSWORD == "RESET_PASSWORD"

    def test_tenant_events_exist(self):
        """Tenant lifecycle events are defined."""
        from app.models.audit_log import AuditEvents
        assert AuditEvents.TENANT_CREATED == "TENANT_CREATED"
        assert AuditEvents.TENANT_DELETED == "TENANT_DELETED"
        assert AuditEvents.TENANT_SUSPENDED == "TENANT_SUSPENDED"
        assert AuditEvents.TENANT_REACTIVATED == "TENANT_REACTIVATED"

    def test_payment_events_exist(self):
        """Payment-related events are defined."""
        from app.models.audit_log import AuditEvents
        assert AuditEvents.PAYMENT_APPROVED == "PAYMENT_APPROVED"
        assert AuditEvents.PAYMENT_REJECTED == "PAYMENT_REJECTED"

    def test_all_events_are_unique(self):
        """All event values should be unique (no duplicates)."""
        from app.models.audit_log import AuditEvents
        events = [
            v for k, v in vars(AuditEvents).items()
            if not k.startswith("_") and isinstance(v, str)
        ]
        assert len(events) == len(set(events)), "Duplicate event values found"

    def test_all_events_non_empty(self):
        """All event values should be non-empty strings."""
        from app.models.audit_log import AuditEvents
        for attr_name in dir(AuditEvents):
            if attr_name.startswith("_"):
                continue
            val = getattr(AuditEvents, attr_name)
            if isinstance(val, str):
                assert len(val) > 0, f"Empty value for {attr_name}"
