"""AdminTenantService — SUPER_ADMIN tenant lifecycle operations.

Extracted from app/routers/admin.py (admin_dashboard, admin_list_tenants,
admin_get_tenant, admin_suspend_tenant, admin_cancel_tenant,
admin_reactivate_tenant, admin_toggle_biometric, admin_delete_tenant).

PURE REFACTOR — logic is identical to the original. Only change is:
  db. → self.db.  (constructor-injected database instance)
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession

from app.database import Collections
from app.models.tenant import SubscriptionStatus
from app.services.cache import get_cache

if TYPE_CHECKING:
    from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class AdminTenantService:
    """Service for SUPER_ADMIN tenant lifecycle operations.

    Constructor receives the database instance for testability.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def get_dashboard(self) -> dict:
        """Estadísticas generales del sistema para el dashboard del SUPER_ADMIN."""
        # Cache: devolver datos cacheados si existen
        cache = get_cache()
        cache_key = "admin_dashboard"
        cached = cache.get(cache_key)
        if cached:
            return cached

        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # ── Crear futures para consultas independientes ────────────────
        # Todas estas coroutines son independientes entre sí y se lanzan en paralelo.
        total_tenants_future = self.db[Collections.TENANTS].count_documents({})
        active_future = self.db[Collections.TENANTS].count_documents(
            {"subscriptionStatus": SubscriptionStatus.ACTIVE}
        )
        pending_payment_future = self.db[Collections.TENANTS].count_documents(
            {"subscriptionStatus": SubscriptionStatus.PENDING_PAYMENT}
        )
        suspended_future = self.db[Collections.TENANTS].count_documents(
            {"subscriptionStatus": SubscriptionStatus.SUSPENDED}
        )
        cancelled_future = self.db[Collections.TENANTS].count_documents(
            {"subscriptionStatus": SubscriptionStatus.CANCELLED}
        )
        expired_future = self.db[Collections.TENANTS].count_documents(
            {"subscriptionStatus": SubscriptionStatus.EXPIRED}
        )

        # Ingresos del mes actual
        revenue_pipeline = [
            {"$match": {"createdAt": {"$gte": month_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        revenue_future = self.db[Collections.TENANT_PAYMENTS].aggregate(revenue_pipeline).to_list(5000)

        # Pagos recientes (últimos 10)
        recent_future = (
            self.db[Collections.TENANT_PAYMENTS]
            .find({}, {"tenantId": 1, "amount": 1, "status": 1, "createdAt": 1, "method": 1})
            .sort("createdAt", -1)
            .limit(10)
            .to_list(10)
        )

        # Tenants por expirar (próximos 7 días)
        expiring_future = self.db[Collections.TENANTS].count_documents({
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "subscriptionEndDate": {
                "$gte": now,
                "$lte": now + timedelta(days=7),
            },
        })

        # ── Ejecutar todas en paralelo ──────────────────────────────────
        (
            total_tenants,
            active,
            pending_payment,
            suspended,
            cancelled,
            expired,
            revenue_cursor,
            recent_cursor,
            expiring_soon,
        ) = await asyncio.gather(
            total_tenants_future,
            active_future,
            pending_payment_future,
            suspended_future,
            cancelled_future,
            expired_future,
            revenue_future,
            recent_future,
            expiring_future,
        )

        monthly_revenue = revenue_cursor[0]["total"] if revenue_cursor else 0.0

        # Batch fetch tenant info for recent payments (depende de recent_cursor)
        tenant_ids = list(set(p["tenantId"] for p in recent_cursor))
        tenant_map = {}
        if tenant_ids:
            tenants_list = await self.db[Collections.TENANTS].find(
                {"tenantId": {"$in": tenant_ids}},
                {"tenantId": 1, "businessName": 1, "businessCode": 1},
            ).to_list(10)
            tenant_map = {t["tenantId"]: t for t in tenants_list}

        recent_payments = []
        for p in recent_cursor:
            p["_id"] = str(p["_id"])
            info = tenant_map.get(p["tenantId"], {})
            p["businessName"] = info.get("businessName", "")
            p["businessCode"] = info.get("businessCode", "")
            recent_payments.append(p)

        result = {
            "total_tenants": total_tenants,
            "active": active,
            "pending_payment": pending_payment,
            "suspended": suspended,
            "cancelled": cancelled,
            "expired": expired,
            "monthly_revenue": monthly_revenue,
            "recent_payments": recent_payments,
            "expiring_soon": expiring_soon,
        }

        # Cachear resultado por 30 segundos
        cache.set(cache_key, result, ttl_seconds=30)
        return result

    async def list_tenants(
        self,
        status: Optional[str],
        plan: Optional[str],
        search: Optional[str],
        page: int,
        limit: int,
    ) -> dict:
        """Listar tenants con filtros opcionales (status, plan, search) y paginación."""
        query = {}

        if status:
            query["subscriptionStatus"] = status.upper()
        if plan:
            query["plan"] = plan.upper()
        if search:
            search_regex = {"$regex": re.escape(search.strip()), "$options": "i"}
            query["$or"] = [
                {"businessName": search_regex},
                {"email": search_regex},
                {"businessCode": search_regex},
            ]

        total = await self.db[Collections.TENANTS].count_documents(query)
        skip = (page - 1) * limit
        cursor = (
            await self.db[Collections.TENANTS]
            .find(query, {"_id": 1, "tenantId": 1, "businessName": 1, "businessCode": 1, "plan": 1, "subscriptionStatus": 1, "createdAt": 1, "email": 1, "subscriptionEndDate": 1, "isDemo": 1, "phone": 1, "address": 1, "city": 1})
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
            .to_list(limit)
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

    async def get_tenant(self, identifier: str) -> dict:
        """Obtener detalle completo de un tenant + resumen de pagos.

        Acepta tanto tenantId (UUID) como businessCode (slug).
        Lanza HTTPException 404 si no se encuentra.
        """
        from fastapi import HTTPException

        tenant = await self.resolve_tenant(identifier)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        tenant["id"] = str(tenant.pop("_id"))

        # Resumen de pagos
        payment_pipeline = [
            {"$match": {"tenantId": tenant["tenantId"]}},
            {"$group": {
                "_id": None,
                "total_paid": {"$sum": "$amount"},
                "last_payment_date": {"$max": "$createdAt"},
            }},
        ]
        payment_summary = await self.db[Collections.TENANT_PAYMENTS].aggregate(payment_pipeline).to_list(1)
        if payment_summary:
            tenant["total_paid"] = payment_summary[0].get("total_paid", 0)
            tenant["last_payment_date"] = payment_summary[0].get("last_payment_date")
        else:
            tenant["total_paid"] = 0
            tenant["last_payment_date"] = None

        return tenant

    async def resolve_tenant(self, identifier: str) -> Optional[dict]:
        """Resuelve un tenant por tenantId (UUID) o businessCode (slug)."""
        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": identifier})
        if not tenant:
            tenant = await self.db[Collections.TENANTS].find_one({"businessCode": identifier})
        return tenant

    async def suspend(self, tenant_id: str, reason: str, audit_service: Optional['AuditService'] = None) -> dict:
        """Suspender un tenant — cambia status a SUSPENDED."""
        from fastapi import HTTPException

        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        await self.db[Collections.TENANTS].update_one(
            {"tenantId": tenant_id},
            {"$set": {
                "subscriptionStatus": SubscriptionStatus.SUSPENDED,
                "suspendReason": reason,
                "updatedAt": datetime.utcnow(),
            }}
        )

        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.TENANT_SUSPENDED,
                actor_id="system",
                actor_type="SUPER_ADMIN",
                tenant_id=tenant_id,
                target_id=tenant_id,
                target_type="tenant",
                details={"businessName": tenant.get("businessName", ""), "reason": reason},
            )

        updated = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        updated["id"] = str(updated.pop("_id"))
        return updated

    async def cancel(self, tenant_id: str, reason: str) -> dict:
        """Cancelar un tenant — cambia status a CANCELLED. Solo si está ACTIVE, SUSPENDED o PENDING_PAYMENT."""
        from fastapi import HTTPException

        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        current_status = tenant.get("subscriptionStatus")
        if current_status not in [
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.PENDING_PAYMENT,
        ]:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede cancelar un tenant con estado {current_status}"
            )

        await self.db[Collections.TENANTS].update_one(
            {"tenantId": tenant_id},
            {"$set": {
                "subscriptionStatus": SubscriptionStatus.CANCELLED,
                "cancelReason": reason,
                "updatedAt": datetime.utcnow(),
            }}
        )

        updated = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        updated["id"] = str(updated.pop("_id"))
        return updated

    async def reactivate(self, tenant_id: str, reason: str, audit_service: Optional['AuditService'] = None) -> dict:
        """Reactivar un tenant — cambia status a ACTIVE. Solo si está SUSPENDED."""
        from fastapi import HTTPException

        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        current_status = tenant.get("subscriptionStatus")
        if current_status != SubscriptionStatus.SUSPENDED:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede reactivar un tenant con estado {current_status}. Usá pago manual para EXPIRED."
            )

        await self.db[Collections.TENANTS].update_one(
            {"tenantId": tenant_id},
            {"$set": {
                "subscriptionStatus": SubscriptionStatus.ACTIVE,
                "reactivateReason": reason,
                "updatedAt": datetime.utcnow(),
            }}
        )

        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.TENANT_REACTIVATED,
                actor_id="system",
                actor_type="SUPER_ADMIN",
                tenant_id=tenant_id,
                target_id=tenant_id,
                target_type="tenant",
                details={"businessName": tenant.get("businessName", ""), "reason": reason},
            )

        updated = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        updated["id"] = str(updated.pop("_id"))
        return updated

    async def toggle_biometric(self, tenant_id: str, enabled: bool) -> dict:
        """Super admin habilita o deshabilita huella biométrica para un tenant."""
        from fastapi import HTTPException

        result = await self.db[Collections.TENANTS].update_one(
            {"tenantId": tenant_id},
            {"$set": {
                "biometricEnabled": enabled,
                "updatedAt": datetime.utcnow(),
            }}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        updated = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        updated["id"] = str(updated.pop("_id"))
        return updated

    async def delete_tenant(self, tenant_id: str, session: Optional[AsyncIOMotorClientSession] = None, audit_service: Optional['AuditService'] = None) -> dict:
        """Elimina un tenant y TODOS sus datos de la base de datos.
        Password verification is handled by the router — this receives tenant_id only.
        
        When session is provided (transaction mode), all writes use the session
        for atomicity. When session is None (fallback mode), writes are direct.
        """
        tenant = await self.db[Collections.TENANTS].find_one({"tenantId": tenant_id}, session=session)
        if not tenant:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        business_name = tenant.get("businessName", "Gimnasio")

        # Eliminar TODOS los datos asociados al tenant
        filter_query = {"tenantId": tenant_id}

        deleted_counts = {}

        # Orden: primero dependencias, después el tenant
        collections_to_delete = [
            (Collections.USERS, "usuarios"),
            (Collections.EMPLOYEES, "empleados"),
            (Collections.CLIENTS, "clientes"),
            (Collections.PRODUCTS, "productos"),
            (Collections.SERVICES, "servicios"),
            (Collections.SALES, "ventas"),
            (Collections.INVOICES, "facturas"),
            (Collections.ATTENDANCE, "asistencias"),
            (Collections.COUNTERS, "contadores"),
            (Collections.TENANT_PAYMENTS, "pagos"),
            (Collections.FINGERPRINTS, "huellas"),
            (Collections.PASSWORD_RESET_TOKENS, "tokens de recuperación"),
        ]

        for collection_name, label in collections_to_delete:
            result = await self.db[collection_name].delete_many(filter_query, session=session)
            if result.deleted_count > 0:
                deleted_counts[label] = result.deleted_count

        # Eliminar el tenant mismo
        result = await self.db[Collections.TENANTS].delete_one(filter_query, session=session)
        deleted_counts["tenant"] = result.deleted_count

        detail = ", ".join(f"{count} {label}" for label, count in deleted_counts.items())

        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.TENANT_DELETED,
                actor_id="system",
                actor_type="SUPER_ADMIN",
                tenant_id=tenant_id,
                target_id=tenant_id,
                target_type="tenant",
                details={"businessName": business_name, "deleted": deleted_counts},
            )

        logger.info(
            "SUPER_ADMIN eliminó tenant %s (%s): %s",
            tenant_id, business_name, detail,
        )

        return {
            "message": f"Tenant '{business_name}' eliminado permanentemente",
            "deleted": deleted_counts,
        }
