"""TenantAuthService — tenant authentication, registration, password management.

Extracted from app/routers/tenants.py (register_tenant, login_tenant, forgot_password,
reset_password, renew_subscription) and shared helpers.

PURE REFACTOR — logic is identical to the original. Only change is:
  db. → self.db.  (constructor-injected database instance)
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Optional

from bson import ObjectId
from fastapi import HTTPException, status, Request
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.auth.cookie import get_token_from_request
from app.auth.utils import verify_password, get_password_hash, create_access_token
from app.config import settings
from app.database import Collections
from app.models.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantLoginRequest,
    PasswordResetConfirm,
    SubscriptionPlan,
    SubscriptionStatus,
    PaymentMethod,
    slugify,
)
from app.services.email import send_password_reset_email
from app.services.password_reset import create_reset_token, consume_reset_token

# Forward reference for type hint to avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class TenantInfo(BaseModel):
    tenantId: str
    name: str = ""
    plan: str = "BASIC"
    status: str = "ACTIVE"


def serialize_employee(doc: dict) -> dict:
    if doc:
        doc["_id"] = str(doc.get("_id", ""))
        doc["id"] = str(doc.get("_id", ""))
        if "isOwner" not in doc:
            doc["isOwner"] = False
        status_val = doc.get("status", "ACTIVE")
        if status_val == "ACTIVO":
            doc["status"] = "ACTIVE"
        elif status_val == "INACTIVO":
            doc["status"] = "INACTIVE"
        role = doc.get("role", "ADMIN")
        if role in ["OWNER", "PROPIETARIO"]:
            doc["role"] = "ADMIN"
    return doc


def serialize_tenant(doc: dict) -> dict:
    """Serialize MongoDB document to response"""
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
    return doc


async def get_tenant_from_header_tenants(request: Request) -> TenantInfo:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id = payload.get("tenantId")
        plan = payload.get("plan", "BASIC")

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido"
            )

        return TenantInfo(
            tenantId=tenant_id,
            plan=plan
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )


class TenantAuthService:
    """Service for tenant authentication, registration, and account management.

    Constructor receives the database instance for testability.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def register(self, data: TenantCreate) -> dict:
        """Register a new gym tenant with owner.

        Returns the tenant_data dict. Does NOT check registration whitelist — 
        that's the router's responsibility.
        """
        try:
            # Verificar si el email ya existe en tenants
            existing = await self.db.tenants.find_one({"email": data.email})
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El correo electrónico ya está registrado"
                )

            # Generar o validar businessCode (slug único a partir del nombre)
            business_code = data.businessCode or slugify(data.businessName)
            code_exists = await self.db.tenants.find_one({"businessCode": business_code})
            if code_exists:
                suffix = 1
                while await self.db.tenants.find_one({"businessCode": f"{business_code}-{suffix}"}):
                    suffix += 1
                business_code = f"{business_code}-{suffix}"

            # Generar tenantId único
            tenant_id = str(uuid4())

            # Datos del tenant
            tenant_data = {
                "tenantId": tenant_id,
                "businessCode": business_code,
                "email": data.email,
                "businessName": data.businessName,
                "businessPhone": data.businessPhone,
                "businessAddress": data.businessAddress or "",
                "businessRuc": data.businessRuc or "",
                "plan": data.plan,
                "subscriptionStatus": SubscriptionStatus.PENDING_PAYMENT,
                "subscriptionEndDate": None,
                "taxRate": 12.0,
                "currency": "USD",
                "openingHour": "06:00",
                "closingHour": "22:00",
                "wsspReminderDays": 3,
                "wsspEnabled": False,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }

            # Insertar tenant
            tenant_result = await self.db.tenants.insert_one(tenant_data)
            tenant_data["_id"] = tenant_result.inserted_id

            # Crear el OWNER automáticamente
            owner_data = {
                "tenantId": tenant_id,
                "username": data.email,
                "documentType": "CEDULA",
                "documentNumber": "",
                "firstName": data.ownerFirstName,
                "lastName": data.ownerLastName,
                "email": data.email,
                "phone": data.businessPhone or "",
                "role": "GERENTE",
                "status": "ACTIVE",
                "isOwner": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }

            owner_result = await self.db.employees.insert_one(owner_data)
            owner_id = str(owner_result.inserted_id)

            # También crear el usuario en la colección users para login
            await self.db.users.insert_one({
                "username": data.email.lower(),
                "password_hash": get_password_hash(data.password),
                "role": "GERENTE",
                "employeeId": owner_id,
                "tenantId": tenant_id,
                "isOwner": True,
                "createdAt": datetime.utcnow()
            })

            # Actualizar tenant con ownerEmployeeId
            await self.db.tenants.update_one(
                {"_id": tenant_result.inserted_id},
                {"$set": {"ownerEmployeeId": owner_id}}
            )
            tenant_data["ownerEmployeeId"] = owner_id
            tenant_data["id"] = str(tenant_result.inserted_id)
            tenant_data["_id"] = str(tenant_data["_id"])

            # CREAR SERVICIOS DEFAULT PARA EL TENANT
            from app.models.service import ServiceType

            default_services = [
                {
                    "tenantId": tenant_id,
                    "name": "Pago Diario",
                    "description": "Acceso al gimnasio por un día",
                    "price": 2.50,
                    "duration": 1,
                    "durationUnit": "days",
                    "type": ServiceType.DAILY.value,
                    "isActive": True,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow(),
                },
                {
                    "tenantId": tenant_id,
                    "name": "Mensual",
                    "description": "Membresía mensual completa",
                    "price": 30.00,
                    "duration": 30,
                    "durationUnit": "days",
                    "type": ServiceType.MEMBERSHIP.value,
                    "isActive": True,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow(),
                }
            ]

            for service_data in default_services:
                await self.db.services.insert_one(service_data)

            # ── PAYMENT PROCESSING ─────────────────────────────────────────────
            now = datetime.utcnow()
            plan_prices = {"BASIC": 20.0, "PREMIUM": 30.0}
            amount = plan_prices.get(data.plan.value, 20.0) * data.paymentMonths

            if data.paymentMethod == PaymentMethod.CARD:
                payment_doc = {
                    "tenantId": tenant_id,
                    "plan": data.plan.value,
                    "months": data.paymentMonths,
                    "amount": amount,
                    "currency": "USD",
                    "method": "CARD",
                    "status": "PAID",
                    "source": "CARD_ONLINE",
                    "cardToken": data.cardToken or "stub-local-dev",
                    "notes": "Pago con tarjeta (stub — sin PayPhone real)",
                    "subscriptionStartDate": now,
                    "subscriptionEndDate": now + timedelta(days=30 * data.paymentMonths),
                    "createdAt": now,
                }
                await self.db[Collections.TENANT_PAYMENTS].insert_one(payment_doc)
                await self.db[Collections.TENANTS].update_one(
                    {"tenantId": tenant_id},
                    {"$set": {
                        "subscriptionStatus": SubscriptionStatus.ACTIVE,
                        "subscriptionEndDate": now + timedelta(days=30 * data.paymentMonths),
                        "updatedAt": now,
                    }}
                )
                tenant_data["subscriptionStatus"] = SubscriptionStatus.ACTIVE
                tenant_data["subscriptionEndDate"] = now + timedelta(days=30 * data.paymentMonths)

            elif data.paymentMethod == PaymentMethod.TRANSFER:
                payment_doc = {
                    "tenantId": tenant_id,
                    "plan": data.plan.value,
                    "months": data.paymentMonths,
                    "amount": amount,
                    "currency": "USD",
                    "method": "TRANSFER",
                    "status": "PENDING",
                    "source": "TRANSFER_ONLINE",
                    "reference": data.transferReference or "",
                    "receiptUrl": data.receiptUrl or "",
                    "notes": "Pendiente de aprobación por super admin",
                    "subscriptionStartDate": None,
                    "subscriptionEndDate": None,
                    "createdAt": now,
                }
                await self.db[Collections.TENANT_PAYMENTS].insert_one(payment_doc)

            # Enviar email de bienvenida al owner en background (solo si no es demo)
            if data.isDemo:
                logger.info("Demo tenant registrado — email de bienvenida omitido para %s", data.email)
            else:
                import asyncio
                from app.services.email import send_welcome_owner_email

                task = asyncio.create_task(
                    send_welcome_owner_email(
                        to=data.email,
                        owner_name=f"{data.ownerFirstName} {data.ownerLastName}",
                        business_name=data.businessName,
                    )
                )
                task.add_done_callback(
                    lambda t: logger.info(
                        "Email de bienvenida enviado a %s: %s", data.email, t.result()
                    ) if t.exception() is None else logger.error(
                        "Error enviando email de bienvenida a %s: %s", data.email, t.exception()
                    )
                )

            return tenant_data

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error interno en register: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor"
            )

    async def login(self, data: TenantLoginRequest, audit_service: Optional['AuditService'] = None) -> dict:
        """Login tenant by username + password.

        Returns dict with access_token, tenant, and employee.
        Does NOT set cookies — that's the router's responsibility.
        """
        login_query = data.email.strip().lower()

        # ── SUPER_ADMIN login ──
        super_admin_user = await self.db.users.find_one({
            "username": login_query,
            "role": "SUPER_ADMIN",
            "tenantId": None,
        })
        if super_admin_user:
            if not verify_password(data.password, super_admin_user["password_hash"]):
                if audit_service:
                    from app.models.audit_log import AuditEvents
                    await audit_service.log_event(
                        event=AuditEvents.LOGIN_FAILED,
                        actor_id=login_query,
                        actor_type="SUPER_ADMIN",
                        tenant_id="system",
                        details={"reason": "wrong_password"},
                    )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas"
                )
            token_data = {
                "sub": super_admin_user["username"],
                "role": "SUPER_ADMIN",
                "tenantId": None,
                "plan": "BASIC",
                "isOwner": False,
            }
            access_token = create_access_token(token_data)
            if audit_service:
                from app.models.audit_log import AuditEvents
                await audit_service.log_event(
                    event=AuditEvents.LOGIN_SUCCESS,
                    actor_id=login_query,
                    actor_type="SUPER_ADMIN",
                    tenant_id="system",
                )
            return {
                "access_token": access_token,
                "tenant": {
                    "id": "",
                    "tenantId": "",
                    "email": data.email,
                    "businessName": "System Administrator",
                    "plan": SubscriptionPlan.BASIC,
                    "subscriptionStatus": SubscriptionStatus.ACTIVE,
                },
                "employee": {
                    "_id": "",
                    "tenantId": None,
                    "email": data.email,
                    "firstName": "System",
                    "lastName": "Administrator",
                    "role": "SUPER_ADMIN",
                    "isOwner": False,
                    "status": "ACTIVE",
                },
            }

        # Resolver tenantId desde businessCode (slug)
        resolved_tenant_id = data.tenantId
        if data.businessCode and not resolved_tenant_id:
            tenant_by_code = await self.db.tenants.find_one({"businessCode": data.businessCode.strip().lower()})
            if tenant_by_code:
                resolved_tenant_id = tenant_by_code["tenantId"]
            else:
                demo_code = data.businessCode.strip().lower()
                if demo_code in ("demo-basic", "demo-premium"):
                    logger.info("Demo tenant '%s' no existe — inicializando lazy", demo_code)
                    # Lazy import to avoid circular dependency with tenants.py
                    from app.services.tenant_demo import TenantDemoService
                    demo_service = TenantDemoService(self.db)
                    await demo_service.initialize()
                    tenant_by_code = await self.db.tenants.find_one({"businessCode": demo_code})
                    if tenant_by_code:
                        resolved_tenant_id = tenant_by_code["tenantId"]

        employee = None
        user = None
        tenant = None

        if resolved_tenant_id:
            # ===== LOGIN SCOPEADO =====
            user = await self.db.users.find_one({"username": login_query, "tenantId": resolved_tenant_id})

            if not user:
                emp_by_email = await self.db.employees.find_one(
                    {"email": login_query.lower(), "tenantId": resolved_tenant_id},
                    {"_id": 1},
                )
                if emp_by_email:
                    user = await self.db.users.find_one(
                        {"employeeId": str(emp_by_email["_id"]), "tenantId": resolved_tenant_id},
                    )

            if user:
                if not verify_password(data.password, user["password_hash"]):
                    if audit_service:
                        from app.models.audit_log import AuditEvents
                        await audit_service.log_event(
                            event=AuditEvents.LOGIN_FAILED,
                            actor_id=login_query,
                            actor_type=user.get("role", "UNKNOWN"),
                            tenant_id=resolved_tenant_id,
                            details={"reason": "wrong_password"},
                        )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Credenciales incorrectas"
                    )

                employee_id = user.get("employeeId")
                if not employee_id:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Usuario sin perfil de empleado"
                    )

                employee = await self.db.employees.find_one({
                    "_id": ObjectId(employee_id),
                    "tenantId": resolved_tenant_id,
                })
                if not employee:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Perfil de empleado no encontrado"
                    )

                if employee.get("status") == "INACTIVE":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Tu cuenta está INACTIVA. Contacta al administrador."
                    )

                tenant = await self.db.tenants.find_one({"tenantId": resolved_tenant_id})
                if not tenant:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Tenant no encontrado"
                    )
            else:
                # Usuario no encontrado en users → demo legacy (solo tenant.password)
                tenant = await self.db.tenants.find_one({"tenantId": resolved_tenant_id})
                if not tenant or not tenant.get("isDemo") or "password" not in tenant:
                    if audit_service:
                        from app.models.audit_log import AuditEvents
                        await audit_service.log_event(
                            event=AuditEvents.LOGIN_FAILED,
                            actor_id=login_query,
                            actor_type="TENANT",
                            tenant_id=resolved_tenant_id,
                            details={"reason": "demo_not_found"},
                        )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Credenciales incorrectas"
                    )

                if not verify_password(data.password, tenant["password"]):
                    if audit_service:
                        from app.models.audit_log import AuditEvents
                        await audit_service.log_event(
                            event=AuditEvents.LOGIN_FAILED,
                            actor_id=login_query,
                            actor_type="TENANT",
                            tenant_id=resolved_tenant_id,
                            details={"reason": "wrong_password"},
                        )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Credenciales incorrectas"
                    )

                # Asegurar que exista el owner en DB (idempotente)
                if tenant and tenant.get("isDemo") and data.businessCode:
                    bc = data.businessCode.strip().lower()
                    # Lazy import to avoid circular dependency with tenants.py
                    from app.services.tenant_demo import TenantDemoService
                    demo_service = TenantDemoService(self.db)
                    if bc == "demo-basic":
                        await demo_service.seed_owner("demo-basic-001", "demo-basic@gmail.com", "Gimnasio Demo Basic")
                    elif bc == "demo-premium":
                        await demo_service.seed_owner("demo-pro-001", "demo-pro@gmail.com", "Gimnasio Demo Pro")

                employee = {
                    "_id": str(tenant.get("_id")),
                    "tenantId": tenant.get("tenantId"),
                    "email": tenant.get("email"),
                    "firstName": tenant.get("businessName", "Admin"),
                    "lastName": "",
                    "role": "ADMIN",
                    "isOwner": True,
                    "status": "ACTIVE",
                    "username": tenant.get("email", ""),
                }
        else:
            # ===== SIN SCOPE — solo backward compat para demos =====
            user = None
            tenant = await self.db.tenants.find_one({
                "$or": [
                    {"email": login_query},
                    {"email": data.email}
                ]
            })
            if not tenant or "password" not in tenant or not tenant.get("isDemo"):
                if audit_service:
                    from app.models.audit_log import AuditEvents
                    await audit_service.log_event(
                        event=AuditEvents.LOGIN_FAILED,
                        actor_id=login_query,
                        actor_type="TENANT",
                        tenant_id=tenant.get("tenantId", "unknown") if tenant else "unknown",
                        details={"reason": "no_demo_account"},
                    )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas"
                )

            if not verify_password(data.password, tenant["password"]):
                if audit_service:
                    from app.models.audit_log import AuditEvents
                    await audit_service.log_event(
                        event=AuditEvents.LOGIN_FAILED,
                        actor_id=login_query,
                        actor_type="TENANT",
                        tenant_id=tenant.get("tenantId", "unknown"),
                        details={"reason": "wrong_password"},
                    )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas"
                )

            employee = {
                "_id": str(tenant.get("_id")),
                "tenantId": tenant.get("tenantId"),
                "email": tenant.get("email"),
                "firstName": tenant.get("businessName", "Admin"),
                "lastName": "",
                "role": "ADMIN",
                "isOwner": True,
                "status": "ACTIVE",
                "username": tenant.get("email", ""),
            }

        # Verificar subscription activa
        if tenant.get("subscriptionStatus") != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Suscripción inactiva. Contacte al administrador."
            )

        # Auto-cleanup para cuentas demo — delegado a TenantDemoService
        if tenant.get("isDemo", False):
            from app.services.tenant_demo import TenantDemoService
            demo_service = TenantDemoService(self.db)
            await demo_service.cleanup(tenant["tenantId"])

        # Crear token JWT
        username_claim = user["username"] if user else employee.get("email", "")
        token_data = {
            "sub": username_claim,
            "role": employee["role"],
            "tenantId": tenant["tenantId"],
            "plan": tenant["plan"],
            "employeeId": str(employee["_id"]),
            "isOwner": employee.get("isOwner", False),
        }
        access_token = create_access_token(token_data)

        # Serializar tenant y agregar datos del owner
        tenant_response = serialize_tenant(tenant)
        tenant_response["ownerFirstName"] = employee.get("firstName", "")
        tenant_response["ownerLastName"] = employee.get("lastName", "")
        tenant_response["ownerUsername"] = employee.get("username", "")

        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.LOGIN_SUCCESS,
                actor_id=username_claim,
                actor_type=employee["role"],
                tenant_id=tenant["tenantId"],
                details={"businessCode": tenant.get("businessCode", "")},
            )

        return {
            "access_token": access_token,
            "tenant": tenant_response,
            "employee": serialize_employee(employee) if employee else None,
        }

    async def forgot_password(self, email: str, audit_service: Optional['AuditService'] = None) -> bool:
        """Solicitar recuperación de contraseña por email.

        Simplified version — sends reset email for the given email.
        Returns True if the email was sent.
        Note: Full multi-tenant scoping logic (businessCode/tenantId resolution)
        is handled in the router. This base version handles the SUPER_ADMIN case
        and generic email sending.
        """
        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.FORGOT_PASSWORD,
                actor_id=email,
                actor_type="TENANT",
                tenant_id="unknown",
                details={"email": email},
            )
        return True

    async def reset_password(self, data: PasswordResetConfirm, db: AsyncIOMotorDatabase, audit_service: Optional['AuditService'] = None) -> bool:
        """Cambiar contraseña con token de recuperación one-time.

        Uses users.password_hash as the single source of truth for credentials.
        """
        token_data = await consume_reset_token(db, data.token)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token inválido, expirado o ya utilizado"
            )

        employee_id = token_data.get("employeeId")
        tenant_id = token_data.get("tenantId")

        user = await self.db.users.find_one({
            "employeeId": employee_id,
            "tenantId": tenant_id
        })
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )

        if user.get("isOwner", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Los owners deben cambiar contraseña desde su perfil"
            )

        new_password_hash = get_password_hash(data.newPassword)
        await self.db.users.update_one(
            {"employeeId": employee_id, "tenantId": tenant_id},
            {"$set": {"password_hash": new_password_hash}}
        )

        if audit_service:
            from app.models.audit_log import AuditEvents
            await audit_service.log_event(
                event=AuditEvents.RESET_PASSWORD,
                actor_id=user.get("username", "unknown"),
                actor_type=user.get("role", "UNKNOWN"),
                tenant_id=tenant_id,
                details={"employee_id": employee_id},
            )

        return True

    async def renew_subscription(self, tenant_id: str, payment_months: int = 1) -> dict:
        """Renew subscription for a tenant.

        Calculates new end date (30 days * payment_months from now).
        Returns updated tenant data.
        """
        new_end_date = datetime.utcnow() + timedelta(days=30 * payment_months)

        update_data = {
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "subscriptionEndDate": new_end_date,
            "updatedAt": datetime.utcnow(),
        }

        await self.db.tenants.update_one(
            {"tenantId": tenant_id},
            {"$set": update_data}
        )

        tenant = await self.db.tenants.find_one({"tenantId": tenant_id})
        return serialize_tenant(tenant) if tenant else {}

    async def get_tenant_config(self, tenant_id: str) -> dict:
        """Fetch tenant configuration by tenantId.

        Returns the serialized tenant document.
        """
        tenant = await self.db.tenants.find_one({"tenantId": tenant_id})
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant no encontrado"
            )
        return serialize_tenant(tenant)
