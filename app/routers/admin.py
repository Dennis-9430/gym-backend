# Admin router — endpoints protegidos para SUPER_ADMIN
# Relacionado con: routers/tenants.py, models/tenant.py, database.py
"""Admin router — SUPER_ADMIN-only tenant lifecycle and payment management"""
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from app.database import get_database, Collections
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse, UserRole
from app.models.tenant import (
    SubscriptionPlan,
    SubscriptionStatus,
    PaymentMethod,
    ManualPaymentCreate,
    ManualPaymentResponse,
    TenantResponse,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


async def require_super_admin(current_user: UserResponse = Depends(get_current_user)):
    """Dependencia que verifica que el usuario autenticado sea SUPER_ADMIN."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Solo SUPER_ADMIN puede acceder a este recurso"
        )
    if current_user.tenantId is not None:
        raise HTTPException(
            status_code=403,
            detail="Solo SUPER_ADMIN puede acceder a este recurso"
        )
    return current_user


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def admin_dashboard(_: UserResponse = Depends(require_super_admin)):
    """Estadísticas generales del sistema para el dashboard del SUPER_ADMIN."""
    db = get_database()

    total_tenants = await db[Collections.TENANTS].count_documents({})
    active = await db[Collections.TENANTS].count_documents(
        {"subscriptionStatus": SubscriptionStatus.ACTIVE}
    )
    pending_payment = await db[Collections.TENANTS].count_documents(
        {"subscriptionStatus": SubscriptionStatus.PENDING_PAYMENT}
    )
    suspended = await db[Collections.TENANTS].count_documents(
        {"subscriptionStatus": SubscriptionStatus.SUSPENDED}
    )
    cancelled = await db[Collections.TENANTS].count_documents(
        {"subscriptionStatus": SubscriptionStatus.CANCELLED}
    )
    expired = await db[Collections.TENANTS].count_documents(
        {"subscriptionStatus": SubscriptionStatus.EXPIRED}
    )

    # Ingresos del mes actual
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {"createdAt": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    revenue_cursor = await db[Collections.TENANT_PAYMENTS].aggregate(pipeline).to_list(None)
    monthly_revenue = revenue_cursor[0]["total"] if revenue_cursor else 0.0

    # Pagos recientes
    recent_cursor = (
        await db[Collections.TENANT_PAYMENTS]
        .find()
        .sort("createdAt", -1)
        .limit(10)
        .to_list(None)
    )
    recent_payments = []
    for p in recent_cursor:
        p["_id"] = str(p["_id"])
        recent_payments.append(p)

    # Tenants por expirar (próximos 7 días)
    expiring_soon = await db[Collections.TENANTS].count_documents({
        "subscriptionStatus": SubscriptionStatus.ACTIVE,
        "subscriptionEndDate": {
            "$gte": now,
            "$lte": now + timedelta(days=7),
        },
    })

    return {
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


# ── List tenants (with filters) ───────────────────────────────────────────────


@router.get("/tenants")
async def admin_list_tenants(
    status: Optional[str] = Query(None),
    plan: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: UserResponse = Depends(require_super_admin),
):
    """Listar tenants con filtros opcionales (status, plan, search) y paginación."""
    db = get_database()
    query = {}

    if status:
        query["subscriptionStatus"] = status.upper()
    if plan:
        query["plan"] = plan.upper()
    if search:
        search_regex = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"businessName": search_regex},
            {"email": search_regex},
            {"businessCode": search_regex},
        ]

    total = await db[Collections.TENANTS].count_documents(query)
    skip = (page - 1) * limit
    cursor = (
        await db[Collections.TENANTS]
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


# ── Tenant detail ─────────────────────────────────────────────────────────────


@router.get("/tenants/{tenant_id}")
async def admin_get_tenant(
    tenant_id: str,
    _: UserResponse = Depends(require_super_admin),
):
    """Obtener detalle completo de un tenant + resumen de pagos."""
    db = get_database()
    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    tenant["id"] = str(tenant.pop("_id"))

    # Resumen de pagos
    payment_pipeline = [
        {"$match": {"tenantId": tenant_id}},
        {"$group": {
            "_id": None,
            "total_paid": {"$sum": "$amount"},
            "last_payment_date": {"$max": "$createdAt"},
        }},
    ]
    payment_summary = await db[Collections.TENANT_PAYMENTS].aggregate(payment_pipeline).to_list(None)
    if payment_summary:
        tenant["total_paid"] = payment_summary[0].get("total_paid", 0)
        tenant["last_payment_date"] = payment_summary[0].get("last_payment_date")
    else:
        tenant["total_paid"] = 0
        tenant["last_payment_date"] = None

    return tenant


# ── Manual payment ────────────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/manual-payment")
async def admin_manual_payment(
    tenant_id: str,
    data: ManualPaymentCreate,
    current_user: UserResponse = Depends(require_super_admin),
):
    """Registrar pago manual para un tenant — lo reactiva/extiende."""
    db = get_database()

    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
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

    # Insertar registro de pago
    payment_doc = {
        "tenantId": tenant_id,
        "plan": data.plan.value,
        "months": data.months,
        "amount": data.amount,
        "currency": data.currency,
        "method": data.method.value,
        "reference": data.reference,
        "notes": data.notes,
        "registeredBy": current_user.username,
        "subscriptionStartDate": start_date,
        "subscriptionEndDate": end_date,
        "status": "PAID",          # 🔒 Pagos manuales siempre confirmados
        "source": "MANUAL",        # 🔑 Diferencia de pagos automáticos futuros
        "createdAt": now,
    }
    payment_result = await db[Collections.TENANT_PAYMENTS].insert_one(payment_doc)
    payment_doc["id"] = str(payment_result.inserted_id)
    payment_doc.pop("_id", None)

    # Actualizar tenant: activar, setear plan y endDate
    await db[Collections.TENANTS].update_one(
        {"tenantId": tenant_id},
        {"$set": {
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "plan": data.plan.value,
            "subscriptionEndDate": end_date,
            "updatedAt": now,
        }}
    )

    return payment_doc


# ── Suspend tenant ────────────────────────────────────────────────────────────


class SuspendRequest(BaseModel):
    reason: str = ""


class CancelRequest(BaseModel):
    reason: str = ""


class ReactivateRequest(BaseModel):
    reason: str = ""


@router.post("/tenants/{tenant_id}/suspend")
async def admin_suspend_tenant(
    tenant_id: str,
    data: SuspendRequest = SuspendRequest(reason=""),
    _: UserResponse = Depends(require_super_admin),
):
    """Suspender un tenant — cambia status a SUSPENDED."""
    db = get_database()

    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    await db[Collections.TENANTS].update_one(
        {"tenantId": tenant_id},
        {"$set": {
            "subscriptionStatus": SubscriptionStatus.SUSPENDED,
            "suspendReason": data.reason,
            "updatedAt": datetime.utcnow(),
        }}
    )

    updated = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    updated["id"] = str(updated.pop("_id"))
    return updated


# ── Cancel tenant ─────────────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/cancel")
async def admin_cancel_tenant(
    tenant_id: str,
    data: CancelRequest = CancelRequest(reason=""),
    _: UserResponse = Depends(require_super_admin),
):
    """Cancelar un tenant — cambia status a CANCELLED. Solo si está ACTIVE, SUSPENDED o PENDING_PAYMENT."""
    db = get_database()

    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
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

    await db[Collections.TENANTS].update_one(
        {"tenantId": tenant_id},
        {"$set": {
            "subscriptionStatus": SubscriptionStatus.CANCELLED,
            "cancelReason": data.reason,
            "updatedAt": datetime.utcnow(),
        }}
    )

    updated = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    updated["id"] = str(updated.pop("_id"))
    return updated


# ── Reactivate tenant ─────────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/reactivate")
async def admin_reactivate_tenant(
    tenant_id: str,
    data: ReactivateRequest = ReactivateRequest(reason=""),
    _: UserResponse = Depends(require_super_admin),
):
    """Reactivar un tenant — cambia status a ACTIVE. Solo si está SUSPENDED."""
    db = get_database()

    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    current_status = tenant.get("subscriptionStatus")
    if current_status != SubscriptionStatus.SUSPENDED:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede reactivar un tenant con estado {current_status}. Usá pago manual para EXPIRED."
        )

    await db[Collections.TENANTS].update_one(
        {"tenantId": tenant_id},
        {"$set": {
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "reactivateReason": data.reason,
            "updatedAt": datetime.utcnow(),
        }}
    )

    updated = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    updated["id"] = str(updated.pop("_id"))
    return updated


# ── Payment history ───────────────────────────────────────────────────────────


@router.get("/tenants/{tenant_id}/payments")
async def admin_tenant_payments(
    tenant_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: UserResponse = Depends(require_super_admin),
):
    """Historial de pagos de un tenant, ordenado por createdAt descendente."""
    db = get_database()

    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    query = {"tenantId": tenant_id}
    total = await db[Collections.TENANT_PAYMENTS].count_documents(query)
    skip = (page - 1) * limit
    cursor = (
        await db[Collections.TENANT_PAYMENTS]
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


# ── Toggle biometric ──────────────────────────────────────────────────────────


class BiometricToggleRequest(BaseModel):
    biometricEnabled: bool


@router.put("/tenants/{tenant_id}/biometric")
async def admin_toggle_biometric(
    tenant_id: str,
    data: BiometricToggleRequest,
    _: UserResponse = Depends(require_super_admin),
):
    """Super admin habilita o deshabilita huella biométrica para un tenant."""
    db = get_database()
    result = await db[Collections.TENANTS].update_one(
        {"tenantId": tenant_id},
        {"$set": {
            "biometricEnabled": data.biometricEnabled,
            "updatedAt": datetime.utcnow(),
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    updated = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    updated["id"] = str(updated.pop("_id"))
    return updated


# ── SUPER_ADMIN credentials ────────────────────────────────────────────────────


class UpdateSuperAdminCredentialsRequest(BaseModel):
    """Request para actualizar credenciales del SUPER_ADMIN via API."""
    email: Optional[str] = None
    current_password: str
    new_password: Optional[str] = None


@router.post("/super-admin/update-credentials")
async def update_super_admin_credentials(
    body: UpdateSuperAdminCredentialsRequest,
    current_user: UserResponse = Depends(require_super_admin),
):
    """Actualiza email y/o contraseña del SUPER_ADMIN.
    
    Requiere contraseña actual para cualquier cambio.
    No requiere reinicio del servidor.
    """
    from app.auth.utils import verify_password, get_password_hash

    db = get_database()

    # Buscar el documento completo del SUPER_ADMIN
    admin_doc = await db[Collections.USERS].find_one({"username": current_user.username})
    if not admin_doc:
        raise HTTPException(status_code=404, detail="SUPER_ADMIN no encontrado en la base de datos")

    # Verificar contraseña actual
    if not verify_password(body.current_password, admin_doc["password_hash"]):
        raise HTTPException(status_code=403, detail="Contraseña actual incorrecta")

    update: dict = {}

    # Actualizar email
    if body.email and body.email.strip().lower() != current_user.username:
        new_email = body.email.strip().lower()
        # Verificar que no esté en uso por otro usuario
        conflict = await db[Collections.USERS].find_one({
            "username": new_email,
            "_id": {"$ne": admin_doc["_id"]},
        })
        if conflict:
            raise HTTPException(status_code=409, detail="El email ya está en uso por otro usuario")
        update["username"] = new_email

    # Actualizar contraseña
    if body.new_password:
        update["password_hash"] = get_password_hash(body.new_password)

    if not update:
        raise HTTPException(status_code=400, detail="No hay cambios que aplicar")

    await db[Collections.USERS].update_one(
        {"_id": admin_doc["_id"]},
        {"$set": update},
    )

    result = []
    if "username" in update:
        result.append(f"email actualizado a {update['username']}")
    if "password_hash" in update:
        result.append("contraseña actualizada")

    return {"message": f"Credenciales actualizadas: {', '.join(result)}"}
