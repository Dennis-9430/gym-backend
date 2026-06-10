"""AuditLog Pydantic model for system audit trail.

Tracks security-relevant actions: logins, tenant lifecycle, payment operations.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


AUDIT_LOGS_COLLECTION = "audit_logs"


class AuditEvents:
    """Constants for audit event types."""

    # Auth events
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    FORGOT_PASSWORD = "FORGOT_PASSWORD"
    RESET_PASSWORD = "RESET_PASSWORD"

    # Tenant lifecycle events
    TENANT_CREATED = "TENANT_CREATED"
    TENANT_DELETED = "TENANT_DELETED"
    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    TENANT_REACTIVATED = "TENANT_REACTIVATED"

    # Payment events
    PAYMENT_APPROVED = "PAYMENT_APPROVED"
    PAYMENT_REJECTED = "PAYMENT_REJECTED"

    # Registration events
    TENANT_REGISTERED = "TENANT_REGISTERED"


class AuditLog(BaseModel):
    """Schema for a single audit log entry.

    Stored in the 'audit_logs' collection.
    """
    event: str
    actor_id: str
    actor_type: str
    tenant_id: str
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    details: dict = Field(default_factory=dict)
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
