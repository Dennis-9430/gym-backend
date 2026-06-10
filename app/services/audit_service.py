"""AuditService — system audit trail logging and querying.

Tracks security-relevant actions (logins, tenant lifecycle, payments)
for compliance and debugging.
"""
import logging
from datetime import datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.audit_log import AuditLog, AUDIT_LOGS_COLLECTION

logger = logging.getLogger(__name__)


class AuditService:
    """Service for writing and querying audit log entries.

    Constructor receives the database instance for testability.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = AUDIT_LOGS_COLLECTION

    async def log_event(
        self,
        event: str,
        actor_id: str,
        actor_type: str,
        tenant_id: str,
        target_id: Optional[str] = None,
        target_type: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> str:
        """Record an audit log entry.

        Returns the string representation of the inserted document's _id.
        """
        log_entry = AuditLog(
            event=event,
            actor_id=actor_id,
            actor_type=actor_type,
            tenant_id=tenant_id,
            target_id=target_id,
            target_type=target_type,
            details=details or {},
            ip_address=ip_address,
        )
        result = await self.db[self.collection].insert_one(log_entry.model_dump())
        return str(result.inserted_id)

    async def query_logs(
        self,
        event: Optional[str] = None,
        actor_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[dict], int]:
        """Query audit logs with optional filters and pagination.

        Returns (items, total) where items are sorted by timestamp descending.
        """
        query: dict = {}

        if event:
            query["event"] = event
        if actor_id:
            query["actor_id"] = actor_id
        if tenant_id:
            query["tenant_id"] = tenant_id

        # Date range filter
        date_filter: dict = {}
        if from_date:
            date_filter["$gte"] = from_date
        if to_date:
            date_filter["$lte"] = to_date
        if date_filter:
            query["timestamp"] = date_filter

        total = await self.db[self.collection].count_documents(query)

        skip = (page - 1) * limit
        cursor = (
            await self.db[self.collection]
            .find(query)
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
            .to_list(limit)
        )

        items = []
        for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            items.append(doc)

        return items, total
