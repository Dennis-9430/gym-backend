"""AdminPaymentService — SUPER_ADMIN payment operations.

Extracted from app/routers/admin.py (admin_manual_payment, admin_tenant_payments,
admin_pending_payments, admin_approve_payment, admin_reject_payment).

PURE REFACTOR — logic is identical to the original. Only change is:
  db. → self.db.  (constructor-injected database instance)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import Collections
from app.models.tenant import SubscriptionStatus

if TYPE_CHECKING:
    from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class AdminPaymentService:
    """Service for SUPER_ADMIN payment operations.

    Constructor receives the database instance for testability.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def manual_payment(
        self,
        tenant_id: str,
        data: "ManualPaymentCreate",
        admin_username: str,
    ) -> dict:
        """Registrar pago manual para un tenant — lo reactiva/extiende.

        Si existe un pago PENDING para este tenant (ej: transferencia online),
        lo actualiza a PAID en vez de crear un duplicado.
        """
        from fastapi import HTTPException
        from app.models.tenant import ManualPaymentCreate

        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        if tenant.get("subscriptionStatus") == SubscriptionStatus.CANCELLED:
            raise HTTPException(
                status_code=400,
                detail="No se pueden registrar pagos en un tenant CANCELLED"
            )

        now = datetime.utcnow()

        # Calcular fechas de suscripción
        current_status = tenant.get("subscriptionStatus")
        current_end = tenant.get("subscriptionEndDate")

        if current_status == SubscriptionStatus.ACTIVE and current_end:
            start_date = max(current_end, now)
        else:
            start_date = now

        end_date = start_date + timedelta(days=30 * data.months)

        # Buscar si existe un pago PENDING previo (ej: transferencia online)
        pending_payment = await self.db[Collections.TENANT_PAYMENTS].find_one(
            {"tenantId": tenant_id, "status": "PENDING"},
            sort=[("createdAt", -1)],
        )

        if pending_payment:
            # Actualizar el PENDING a PAID en vez de crear duplicado
            update_fields = {
                "status": "PAID",
                "plan": data.plan.value,
                "months": data.months,
                "amount": data.amount,
                "currency": data.currency,
                "method": data.method.value,
                "reference": data.reference or "",
                "notes": data.notes or pending_payment.get("notes", ""),
                "registeredBy": admin_username,
                "approvedBy": admin_username,
                "subscriptionStartDate": start_date,
                "subscriptionEndDate": end_date,
                "source": "MANUAL",
                "updatedAt": now,
            }
            await self.db[Collections.TENANT_PAYMENTS].update_one(
                {"_id": pending_payment["_id"]},
                {"$set": update_fields},
            )
            payment_doc = {**pending_payment, **update_fields}
            payment_doc["id"] = str(payment_doc.pop("_id"))
        else:
            # Insertar nuevo registro de pago
            payment_doc = {
                "tenantId": tenant_id,
                "plan": data.plan.value,
                "months": data.months,
                "amount": data.amount,
                "currency": data.currency,
                "method": data.method.value,
                "reference": data.reference,
                "notes": data.notes,
                "registeredBy": admin_username,
                "subscriptionStartDate": start_date,
                "subscriptionEndDate": end_date,
                "status": "PAID",
                "source": "MANUAL",
                "createdAt": now,
            }
            payment_result = await self.db[Collections.TENANT_PAYMENTS].insert_one(payment_doc)
            payment_doc["id"] = str(payment_result.inserted_id)
            payment_doc.pop("_id", None)

        # Actualizar tenant: activar, setear plan y endDate
        await self.db[Collections.TENANTS].update_one(
            {"tenantId": tenant_id},
            {"$set": {
                "subscriptionStatus": SubscriptionStatus.ACTIVE,
                "plan": data.plan.value,
                "subscriptionEndDate": end_date,
                "updatedAt": now,
            }}
        )

        return payment_doc

    async def list_payments(self, identifier: str, page: int, limit: int) -> dict:
        """Historial de pagos de un tenant, ordenado por createdAt descendente.

        Acepta tanto tenantId (UUID) como businessCode (slug).
        """
        from fastapi import HTTPException

        # Use resolve_tenant helper — try tenantId first, then businessCode
        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": identifier})
        if not tenant:
            tenant = await self.db[Collections.TENANTS].find_one({"businessCode": identifier})
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        tenant_id = tenant["tenantId"]

        query = {"tenantId": tenant_id}
        total = await self.db[Collections.TENANT_PAYMENTS].count_documents(query)
        skip = (page - 1) * limit
        cursor = (
            await self.db[Collections.TENANT_PAYMENTS]
            .find(query)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
            .to_list(None)
        )

        items = []
        for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            items.append(doc)

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    async def list_pending_payments(self, page: int, limit: int) -> dict:
        """Listar pagos por transferencia pendientes de aprobación."""
        query = {"method": "TRANSFER", "status": "PENDING"}
        total = await self.db[Collections.TENANT_PAYMENTS].count_documents(query)
        skip = (page - 1) * limit
        cursor = (
            await self.db[Collections.TENANT_PAYMENTS]
            .find(query)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
            .to_list(None)
        )

        # Batch fetch tenant info
        tenant_ids = list(set(doc["tenantId"] for doc in cursor))
        tenant_map = {}
        if tenant_ids:
            tenants_list = await self.db[Collections.TENANTS].find(
                {"tenantId": {"$in": tenant_ids}},
                {"tenantId": 1, "businessName": 1, "businessCode": 1, "email": 1},
            ).to_list(None)
            tenant_map = {t["tenantId"]: t for t in tenants_list}

        items = []
        for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            info = tenant_map.get(doc["tenantId"], {})
            doc["tenantName"] = info.get("businessName", "")
            doc["tenantEmail"] = info.get("email", "")
            doc["businessCode"] = info.get("businessCode", "")
            items.append(doc)

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    async def approve_payment(self, tenant_id: str, notes: str, admin_username: str, audit_service: Optional['AuditService'] = None) -> dict:
        """Aprobar transferencia pendiente → activa al tenant."""
        from fastapi import HTTPException

        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        # Buscar el payment PENDING más reciente
        pending_payment = (
            await self.db[Collections.TENANT_PAYMENTS]
            .find_one({"tenantId": tenant_id, "method": "TRANSFER", "status": "PENDING"},
                      sort=[("createdAt", -1)])
        )
        if not pending_payment:
            raise HTTPException(status_code=404, detail="No hay pagos por transferencia pendientes")

        now = datetime.utcnow()
        months = pending_payment.get("months", 1)
        end_date = now + timedelta(days=30 * months)

        # Marcar payment como PAID
        await self.db[Collections.TENANT_PAYMENTS].update_one(
            {"_id": pending_payment["_id"]},
            {"$set": {
                "status": "PAID",
                "subscriptionStartDate": now,
                "subscriptionEndDate": end_date,
                "approvedBy": admin_username,
                "approvedAt": now,
                "notes": notes or pending_payment.get("notes", ""),
                "updatedAt": now,
            }}
        )

        # Activar tenant
        await self.db[Collections.TENANTS].update_one(
            {"tenantId": tenant_id},
            {"$set": {
                "subscriptionStatus": SubscriptionStatus.ACTIVE,
                "plan": pending_payment.get("plan", tenant.get("plan", "BASIC")),
                "subscriptionEndDate": end_date,
                "updatedAt": now,
            }}
        )

        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.PAYMENT_APPROVED,
                actor_id=admin_username,
                actor_type="SUPER_ADMIN",
                tenant_id=tenant_id,
                target_id=tenant_id,
                target_type="tenant",
                details={
                    "businessName": tenant.get("businessName", ""),
                    "amount": float(pending_payment.get("amount", 0)),
                    "method": "TRANSFER",
                    "notes": notes,
                },
                ip_address=None,
            )

        return {"message": "Pago aprobado y tenant activado", "tenantId": tenant_id}

    async def reject_payment(self, tenant_id: str, reason: str, admin_username: str, audit_service: Optional['AuditService'] = None) -> dict:
        """Rechazar transferencia pendiente."""
        from fastapi import HTTPException

        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        pending_payment = (
            await self.db[Collections.TENANT_PAYMENTS]
            .find_one({"tenantId": tenant_id, "method": "TRANSFER", "status": "PENDING"},
                      sort=[("createdAt", -1)])
        )
        if not pending_payment:
            raise HTTPException(status_code=404, detail="No hay pagos por transferencia pendientes")

        now = datetime.utcnow()

        # Marcar payment como REJECTED
        await self.db[Collections.TENANT_PAYMENTS].update_one(
            {"_id": pending_payment["_id"]},
            {"$set": {
                "status": "REJECTED",
                "rejectReason": reason,
                "rejectedBy": admin_username,
                "rejectedAt": now,
                "updatedAt": now,
            }}
        )

        # Dejar tenant como PENDING_PAYMENT (no cancelar — puede reintentar)
        await self.db[Collections.TENANTS].update_one(
            {"tenantId": tenant_id},
            {"$set": {
                "updatedAt": now,
            }}
        )

        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.PAYMENT_REJECTED,
                actor_id=admin_username,
                actor_type="SUPER_ADMIN",
                tenant_id=tenant_id,
                target_id=tenant_id,
                target_type="tenant",
                details={
                    "businessName": tenant.get("businessName", ""),
                    "amount": float(pending_payment.get("amount", 0)),
                    "method": "TRANSFER",
                    "reason": reason,
                },
            )

        return {"message": "Pago rechazado", "tenantId": tenant_id}
