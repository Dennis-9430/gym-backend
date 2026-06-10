# Router para Tenants (Gimnasios)
# Relacionado con: models/tenant.py, database.py, main.py
"""Tenant (Gym) API router — thin controllers delegating to TenantAuthService"""
import logging
from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, status, Response
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_database, Collections
from app.config import settings
from app.models.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantLoginRequest,
    TenantLoginResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from app.models.employee import EmployeeResponse, EmployeeUpdate
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.auth.cookie import set_auth_cookie, clear_auth_cookie
from app.services.db_utils import TransactionManager
from app.services.tenant_auth import (
    TenantAuthService,
    TenantInfo,
    serialize_tenant,
    serialize_employee,
    get_tenant_from_header_tenants,
)
from app.services.email import send_password_reset_email
from app.services.password_reset import create_reset_token
from app.services.audit_service import AuditService
from app.models.audit_log import AuditEvents

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

# Whitelist de emails autorizados para registro anticipado
REGISTRATION_WHITELIST = {"dennischapu94@gmail.com"}


@router.post("/register", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(data: TenantCreate):
    # Solo emails whitelisted pueden registrar — early access control
    if data.email.lower().strip() not in REGISTRATION_WHITELIST:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registro en desarrollo — solo disponible para correos autorizados."
        )

    db = get_database()
    auth_service = TenantAuthService(db)

    tx = TransactionManager(db, settings.MONGODB_TRANSACTIONS_ENABLED)
    async with tx as session:
        tenant_data = await auth_service.register(data, session=session)

    # Audit log: tenant registration
    try:
        audit_service = AuditService(db)
        await audit_service.log_event(
            event=AuditEvents.TENANT_REGISTERED,
            actor_id=tenant_data.get("tenantId", "unknown"),
            actor_type="TENANT",
            tenant_id=tenant_data.get("tenantId", "unknown"),
            target_id=tenant_data.get("tenantId"),
            target_type="tenant",
            details={
                "businessName": data.businessName,
                "email": data.email,
                "plan": data.plan.value,
            },
        )
    except Exception:
        logger.warning("Failed to log audit event for tenant registration", exc_info=True)

    return TenantResponse(**tenant_data)


@router.post("/login", response_model=TenantLoginResponse)
async def login_tenant(data: TenantLoginRequest, response: Response):
    db = get_database()
    auth_service = TenantAuthService(db)
    result = await auth_service.login(data)

    # Setear cookie HttpOnly con el JWT (segura contra XSS)
    set_auth_cookie(response, result["access_token"])

    return TenantLoginResponse(
        accessToken=result["access_token"],
        tenant=TenantResponse(**result["tenant"])
    )


@router.post("/logout")
async def logout_tenant(response: Response):
    """Cerrar sesión — elimina la cookie HttpOnly.
    El frontend también debe limpiar localStorage (clearAuthStorage).
    """
    clear_auth_cookie(response)
    return {"message": "Sesión cerrada correctamente"}


# Recuperación de contraseña
@router.post("/forgot-password")
async def forgot_password(data: PasswordResetRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Solicitar recuperación de contraseña por email — requiere businessCode o tenantId"""
    # ── SUPER_ADMIN: permitir reset sin businessCode/tenantId ──
    if not data.businessCode and not data.tenantId:
        email_lower = data.email.strip().lower()
        super_admin = await db.users.find_one({
            "username": email_lower,
            "role": "SUPER_ADMIN",
            "tenantId": None,
        })
        if super_admin:
            raw_token = await create_reset_token(
                db=db,
                username=super_admin["username"],
                tenant_id=None,
                employee_id=None,
            )
            frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
            reset_link = f"{frontend_url}/reset-password?token={raw_token}"
            import asyncio
            asyncio.create_task(
                send_password_reset_email(
                    to=super_admin["username"],
                    reset_link=reset_link,
                    business_name="System Administrator",
                )
            )
            return {"message": "Si el correo existe, recibirás un enlace de recuperación"}
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}

    # Resolver tenantId desde businessCode si se envió
    resolved_tenant_id = data.tenantId
    tenant_doc = None
    if data.businessCode and not resolved_tenant_id:
        tenant_doc = await db.tenants.find_one({"businessCode": data.businessCode.strip().lower()})
        if tenant_doc:
            resolved_tenant_id = tenant_doc["tenantId"]

    if not resolved_tenant_id:
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}

    if not tenant_doc:
        tenant_doc = await db.tenants.find_one({"tenantId": resolved_tenant_id})

    user_query = {"username": data.email.strip().lower(), "tenantId": resolved_tenant_id}
    user = await db.users.find_one(user_query)
    if not user:
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}

    employee = await db.employees.find_one({
        "tenantId": user.get("tenantId"),
        "username": user.get("username"),
    })
    employee_id = str(employee["_id"]) if employee else user.get("employeeId")

    raw_token = await create_reset_token(
        db=db,
        username=user["username"],
        tenant_id=user.get("tenantId"),
        employee_id=employee_id,
    )

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    reset_link = f"{frontend_url}/reset-password?token={raw_token}&tenantId={user.get('tenantId')}"

    tenant_name = tenant_doc.get("businessName", "Gimnasio") if tenant_doc else "Gimnasio"

    import asyncio
    asyncio.create_task(
        send_password_reset_email(
            to=user["username"] if "@" in user["username"] else f"{user['username']}@{tenant_name.lower().replace(' ', '')}.com",
            reset_link=reset_link,
            business_name=tenant_name,
        )
    )

    return {
        "message": "Si el correo existe, recibirás un enlace de recuperación",
    }


@router.post("/reset-password")
async def reset_password(data: PasswordResetConfirm, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Cambiar contraseña con token de recuperación one-time — usando users.password_hash"""
    auth_service = TenantAuthService(db)
    await auth_service.reset_password(data, db)
    return {"message": "Contraseña actualizada correctamente"}


@router.get("/me", response_model=TenantResponse)
async def get_current_tenant(current_user: UserResponse = Depends(get_current_user)):
    db = get_database()
    tenant_id = current_user.tenantId

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sin tenant asociado"
        )

    auth_service = TenantAuthService(db)
    tenant_data = await auth_service.get_tenant_config(tenant_id)
    return TenantResponse(**tenant_data)


@router.put("/me", response_model=TenantResponse)
async def update_current_tenant(data: TenantUpdate, current_user: UserResponse = Depends(get_current_user)):
    db = get_database()
    tenant_id = current_user.tenantId

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sin tenant asociado"
        )

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updatedAt"] = datetime.utcnow()

    await db.tenants.update_one(
        {"tenantId": tenant_id},
        {"$set": update_data}
    )

    tenant = await db.tenants.find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado"
        )

    return TenantResponse(**serialize_tenant(tenant))


@router.post("/renew", response_model=TenantResponse)
async def renew_subscription(
    data: TenantUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    """Renew subscription"""
    if not current_user.isOwner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner puede renovar la suscripción"
        )

    db = get_database()
    tenant_id = current_user.tenantId
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sin tenant asociado"
        )

    tenant = await db.tenants.find_one({"tenantId": tenant_id})
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado"
        )

    auth_service = TenantAuthService(db)
    tenant_data = await auth_service.renew_subscription(tenant_id, payment_months=1)

    if data.plan:
        await db.tenants.update_one(
            {"tenantId": tenant_id},
            {"$set": {"plan": data.plan}}
        )

    # Re-fetch after potential plan update
    tenant = await db.tenants.find_one({"tenantId": tenant_id})
    return TenantResponse(**serialize_tenant(tenant))


@router.get("/plans")
async def get_plans():
    """Get available subscription plans"""
    return {
        "plans": [
            {
                "id": "BASIC",
                "name": "Basic",
                "price": 20,
                "features": [
                    "Clientes",
                    "Membres&#237;as",
                    "Productos",
                    "POS/Ventas",
                    "Asistencia"
                ]
            },
            {
                "id": "PREMIUM",
                "name": "Premium",
                "price": 30,
                "features": [
                    "Clientes",
                    "Membres&#237;as",
                    "Productos",
                    "POS/Ventas",
                    "Asistencia",
                    "Empleados (CRUD)",
                    "Reportes Financieros",
                    "Configuraci&#243;n Completa"
                ]
            }
        ]
    }


@router.put("/owner", response_model=EmployeeResponse)
async def update_owner(
    update_data: EmployeeUpdate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantInfo = Depends(get_tenant_from_header_tenants)
):
    """Actualizar datos del owner (solo el propio owner puede actualizarse)"""
    from app.auth.utils import get_password_hash

    db = get_database()

    if not current_user.isOwner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner puede actualizar sus datos"
        )

    owner_employee_id = current_user.employeeId
    if not owner_employee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se encontr&#243; el ID del owner"
        )

    owner = await db[Collections.EMPLOYEES].find_one({
        "_id": ObjectId(owner_employee_id),
        "tenantId": tenant.tenantId
    })

    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner no encontrado"
        )

    # Campos protegidos - no se pueden cambiar
    protected_fields = ["email", "role", "status", "isOwner", "tenantId"]
    update_dict = update_data.model_dump(exclude_unset=True)

    for field in protected_fields:
        if field in update_dict:
            del update_dict[field]

    # Campos permitidos para el owner (password NO va en employees)
    allowed_fields = ["firstName", "lastName", "phone", "address", "documentNumber", "documentType", "notes", "username"]
    final_update = {k: v for k, v in update_dict.items() if k in allowed_fields and v is not None}

    # Tambi&#233;n actualizar el usuario en la colecci&#243;n users
    user_update = {}
    if "username" in update_dict:
        user_update["username"] = update_dict["username"].lower()
    if "password" in update_dict and update_dict["password"]:
        user_update["password_hash"] = get_password_hash(update_dict["password"])

    if not final_update and not user_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionaron campos v&#225;lidos para actualizar"
        )

    if user_update:
        await db[Collections.USERS].update_one(
            {"employeeId": owner_employee_id, "tenantId": tenant.tenantId},
            {"$set": user_update}
        )

    if final_update:
        final_update["updatedAt"] = datetime.utcnow()
        await db[Collections.EMPLOYEES].update_one(
            {"_id": ObjectId(owner_employee_id), "tenantId": tenant.tenantId},
            {"$set": final_update}
        )

    updated_owner = await db[Collections.EMPLOYEES].find_one({
        "_id": ObjectId(owner_employee_id),
        "tenantId": tenant.tenantId
    })

    return EmployeeResponse(**serialize_employee(updated_owner))


@router.get("/owner", response_model=EmployeeResponse)
async def get_owner(
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantInfo = Depends(get_tenant_from_header_tenants)
):
    """Obtener datos del owner actual"""
    db = get_database()

    owner_employee_id = current_user.employeeId
    if not owner_employee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se encontr&#243; el ID del owner"
        )

    owner = await db[Collections.EMPLOYEES].find_one({
        "_id": ObjectId(owner_employee_id),
        "tenantId": tenant.tenantId
    })

    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner no encontrado"
        )

    return EmployeeResponse(**serialize_employee(owner))


async def get_current_tenant_from_token(authorization: str = None):
    db = get_database()
    """Extract tenant from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )

    token = authorization.replace("Bearer ", "")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id = payload.get("tenantId")

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inv&#225;lido"
            )

        tenant = await db.tenants.find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant no encontrado"
            )

        return serialize_tenant(tenant)

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inv&#225;lido"
        )
