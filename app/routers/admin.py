"""Admin router — SUPER_ADMIN-only tenant lifecycle and payment management.

Thin FastAPI controllers delegating to AdminTenantService and AdminPaymentService.
"""
import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)
from app.database import get_database, Collections
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse, UserRole
from app.models.tenant import (
    SubscriptionPlan,
    SubscriptionStatus,
    PaymentMethod,
    PaymentStatus,
    ManualPaymentCreate,
    ManualPaymentResponse,
    PendingPaymentResponse,
    ApprovePaymentRequest,
    RejectPaymentRequest,
    TenantResponse,
)
from app.config import settings
from app.services.admin_tenant import AdminTenantService
from app.services.admin_payment import AdminPaymentService
from app.services.audit_service import AuditService
from app.services.db_utils import TransactionManager

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


# ── Pydantic request models ──────────────────────────────────────────────────


class SuspendRequest(BaseModel):
    reason: str = ""


class CancelRequest(BaseModel):
    reason: str = ""


class ReactivateRequest(BaseModel):
    reason: str = ""


class BiometricToggleRequest(BaseModel):
    biometricEnabled: bool


class DeleteTenantRequest(BaseModel):
    """Request para eliminar un tenant — requiere contraseña del SUPER_ADMIN."""
    password: str


class UpdateSuperAdminCredentialsRequest(BaseModel):
    """Request para actualizar credenciales del SUPER_ADMIN via API."""
    email: Optional[str] = None
    current_password: str
    new_password: Optional[str] = None


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def admin_dashboard(_: UserResponse = Depends(require_super_admin)):
    """Estadísticas generales del sistema para el dashboard del SUPER_ADMIN."""
    service = AdminTenantService(get_database())
    return await service.get_dashboard()


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
    service = AdminTenantService(get_database())
    return await service.list_tenants(status, plan, search, page, limit)


# ── Tenant detail ─────────────────────────────────────────────────────────────


@router.get("/tenants/{identifier}")
async def admin_get_tenant(
    identifier: str,
    _: UserResponse = Depends(require_super_admin),
):
    """Obtener detalle completo de un tenant + resumen de pagos.

    Acepta tanto tenantId (UUID) como businessCode (slug).
    """
    service = AdminTenantService(get_database())
    return await service.get_tenant(identifier)


# ── Manual payment ────────────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/manual-payment")
async def admin_manual_payment(
    tenant_id: str,
    data: ManualPaymentCreate,
    current_user: UserResponse = Depends(require_super_admin),
):
    """Registrar pago manual para un tenant — lo reactiva/extiende."""
    service = AdminPaymentService(get_database())
    return await service.manual_payment(tenant_id, data, current_user.username)


# ── Suspend tenant ────────────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/suspend")
async def admin_suspend_tenant(
    tenant_id: str,
    data: SuspendRequest = SuspendRequest(reason=""),
    current_user: UserResponse = Depends(require_super_admin),
):
    """Suspender un tenant — cambia status a SUSPENDED."""
    db = get_database()
    service = AdminTenantService(db)
    audit_service = AuditService(db)
    return await service.suspend(tenant_id, data.reason, audit_service=audit_service)


# ── Cancel tenant ─────────────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/cancel")
async def admin_cancel_tenant(
    tenant_id: str,
    data: CancelRequest = CancelRequest(reason=""),
    _: UserResponse = Depends(require_super_admin),
):
    """Cancelar un tenant — cambia status a CANCELLED."""
    service = AdminTenantService(get_database())
    return await service.cancel(tenant_id, data.reason)


# ── Reactivate tenant ─────────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/reactivate")
async def admin_reactivate_tenant(
    tenant_id: str,
    data: ReactivateRequest = ReactivateRequest(reason=""),
    current_user: UserResponse = Depends(require_super_admin),
):
    """Reactivar un tenant — cambia status a ACTIVE. Solo si está SUSPENDED."""
    db = get_database()
    service = AdminTenantService(db)
    audit_service = AuditService(db)
    return await service.reactivate(tenant_id, data.reason, audit_service=audit_service)


# ── Payment history ───────────────────────────────────────────────────────────


@router.get("/tenants/{identifier}/payments")
async def admin_tenant_payments(
    identifier: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: UserResponse = Depends(require_super_admin),
):
    """Historial de pagos de un tenant, ordenado por createdAt descendente."""
    service = AdminPaymentService(get_database())
    return await service.list_payments(identifier, page, limit)


# ── Toggle biometric ──────────────────────────────────────────────────────────


@router.put("/tenants/{tenant_id}/biometric")
async def admin_toggle_biometric(
    tenant_id: str,
    data: BiometricToggleRequest,
    _: UserResponse = Depends(require_super_admin),
):
    """Super admin habilita o deshabilita huella biométrica para un tenant."""
    service = AdminTenantService(get_database())
    return await service.toggle_biometric(tenant_id, data.biometricEnabled)


# ── SUPER_ADMIN credentials ────────────────────────────────────────────────────


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
    admin_doc = await db[Collections.USERS].find_one({
        "username": current_user.username,
        "role": UserRole.SUPER_ADMIN,
        "tenantId": None,
    })
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


# ── Pending transfers (super admin approval) ─────────────────────────────────


@router.get("/payments/pending")
async def admin_pending_payments(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: UserResponse = Depends(require_super_admin),
):
    """Listar pagos por transferencia pendientes de aprobación."""
    service = AdminPaymentService(get_database())
    return await service.list_pending_payments(page, limit)


@router.post("/tenants/{tenant_id}/approve-payment")
async def admin_approve_payment(
    tenant_id: str,
    data: ApprovePaymentRequest = ApprovePaymentRequest(notes=""),
    current_user: UserResponse = Depends(require_super_admin),
):
    """Aprobar transferencia pendiente → activa al tenant."""
    db = get_database()
    service = AdminPaymentService(db)
    audit_service = AuditService(db)
    tx = TransactionManager(db, settings.MONGODB_TRANSACTIONS_ENABLED)
    async with tx as session:
        result = await service.approve_payment(tenant_id, data.notes, current_user.username, session=session, audit_service=audit_service)
    return result


@router.post("/tenants/{tenant_id}/reject-payment")
async def admin_reject_payment(
    tenant_id: str,
    data: RejectPaymentRequest,
    current_user: UserResponse = Depends(require_super_admin),
):
    """Rechazar transferencia pendiente."""
    db = get_database()
    service = AdminPaymentService(db)
    audit_service = AuditService(db)
    return await service.reject_payment(tenant_id, data.reason, current_user.username, audit_service=audit_service)


# ── Delete tenant (full data wipe) ─────────────────────────────────────────────


@router.delete("/tenants/{tenant_id}")
async def admin_delete_tenant(
    tenant_id: str,
    body: DeleteTenantRequest,
    current_user: UserResponse = Depends(require_super_admin),
):
    """Elimina un tenant y TODOS sus datos de la base de datos.

    Requiere contraseña del SUPER_ADMIN como confirmación.
    Esta operación es IRREVERSIBLE.
    """
    from app.auth.utils import verify_password

    db = get_database()

    # 1. Verificar que el tenant existe
    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    # 2. Verificar contraseña del SUPER_ADMIN
    admin_doc = await db[Collections.USERS].find_one({
        "username": current_user.username,
        "role": UserRole.SUPER_ADMIN,
        "tenantId": None,
    })
    if not admin_doc:
        raise HTTPException(status_code=404, detail="SUPER_ADMIN no encontrado en la base de datos")
    if not verify_password(body.password, admin_doc["password_hash"]):
        raise HTTPException(status_code=403, detail="Contraseña incorrecta")

    # 3. Delegar eliminación al servicio
    service = AdminTenantService(db)
    audit_service = AuditService(db)
    tx = TransactionManager(db, settings.MONGODB_TRANSACTIONS_ENABLED)
    async with tx as session:
        result = await service.delete_tenant(tenant_id, session=session, audit_service=audit_service)
    return result


# ── Audit logs ────────────────────────────────────────────────────────────────


@router.get("/audit-logs")
async def admin_audit_logs(
    event: Optional[str] = Query(None, description="Filtrar por tipo de evento (ej: LOGIN_SUCCESS, TENANT_SUSPENDED)"),
    actor_id: Optional[str] = Query(None, description="Filtrar por ID del actor"),
    tenant_id: Optional[str] = Query(None, description="Filtrar por tenantId"),
    from_date: Optional[str] = Query(None, alias="from", description="Fecha desde (YYYY-MM-DDTHH:MM:SS)"),
    to_date: Optional[str] = Query(None, alias="to", description="Fecha hasta (YYYY-MM-DDTHH:MM:SS)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: UserResponse = Depends(require_super_admin),
):
    """Consultar logs de auditoría con filtros opcionales.

    Solo accesible por SUPER_ADMIN. Los logs se ordenan por timestamp descendente.
    """
    from datetime import datetime

    db = get_database()
    audit_service = AuditService(db)

    # Parsear fechas si vienen como string
    from_dt = None
    to_dt = None
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato inválido para 'from'. Usá ISO 8601 (ej: 2025-01-01T00:00:00)")
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato inválido para 'to'. Usá ISO 8601 (ej: 2025-01-01T00:00:00)")

    return await audit_service.query_logs(
        event=event,
        actor_id=actor_id,
        tenant_id=tenant_id,
        from_date=from_dt,
        to_date=to_dt,
        page=page,
        limit=limit,
    )
