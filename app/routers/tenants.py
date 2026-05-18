# Router para Tenants (Gimnasios)
# Relacionado con: models/tenant.py, database.py, main.py
"""Tenant (Gym) API router"""
from datetime import datetime, timedelta
from uuid import uuid4
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, status, Header
from pydantic import BaseModel
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
    SubscriptionPlan,
    SubscriptionStatus,
    slugify,
)
from app.models.employee import EmployeeResponse, EmployeeUpdate
from app.auth.utils import verify_password, get_password_hash, create_access_token
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


class TenantInfo(BaseModel):
    tenantId: str
    name: str = ""
    plan: str = "BASIC"
    status: str = "ACTIVE"


async def get_tenant_from_header_tenants(authorization: str = Header(None)) -> TenantInfo:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )
    
    token = authorization.replace("Bearer ", "")
    
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


def serialize_employee(doc: dict) -> dict:
    if doc:
        doc["_id"] = str(doc.get("_id", ""))
        doc["id"] = str(doc.get("_id", ""))
        if "isOwner" not in doc:
            doc["isOwner"] = False
        status = doc.get("status", "ACTIVE")
        if status == "ACTIVO":
            doc["status"] = "ACTIVE"
        elif status == "INACTIVO":
            doc["status"] = "INACTIVE"
        role = doc.get("role", "ADMIN")
        if role in ["OWNER", "PROPIETARIO"]:
            doc["role"] = "ADMIN"
    return doc


def serialize_tenant(doc: dict) -> dict:
    # Convierte documento de MongoDB a respuesta
    """Serialize MongoDB document to response"""
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
    return doc


@router.post("/register", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(data: TenantCreate):
    # Registro de nuevo tenant (gimnasio) con owner automático
    db = get_database()
    """Register a new gym tenant with owner"""
    try:
        # Verificar si el email ya existe en tenants
        existing = await db.tenants.find_one({"email": data.email})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ya está registrado"
            )
        
        # Generar o validar businessCode (slug único a partir del nombre)
        business_code = data.businessCode or slugify(data.businessName)
        code_exists = await db.tenants.find_one({"businessCode": business_code})
        if code_exists:
            # Si el slug ya existe, agregar sufijo numérico
            suffix = 1
            while await db.tenants.find_one({"businessCode": f"{business_code}-{suffix}"}):
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
            "subscriptionStatus": SubscriptionStatus.ACTIVE,  # Temporal: activo inmediatamente
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
        tenant_result = await db.tenants.insert_one(tenant_data)
        tenant_data["_id"] = tenant_result.inserted_id
        
        # Crear el OWNER automáticamente (sin password — employees es solo perfil)
        owner_data = {
            "tenantId": tenant_id,
            "username": data.email,  # Username inicial = email
            "documentType": "CEDULA",
            "documentNumber": "",
            "firstName": data.ownerFirstName,
            "lastName": data.ownerLastName,
            "email": data.email,  # Mismo email que tenant
            "phone": data.businessPhone or "",
            "role": "GERENTE",  # El owner siempre es GERENTE
            "status": "ACTIVE",  # Usar status, no isActive
            "isOwner": True,  # Flag de owner
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        
        # Insertar employee (owner)
        owner_result = await db.employees.insert_one(owner_data)
        owner_id = str(owner_result.inserted_id)
        
        # También crear el usuario en la colección users para login
        await db.users.insert_one({
            "username": data.email.lower(),  # Username = email
            "password_hash": get_password_hash(data.password),  # Misma contraseña
            "role": "GERENTE",
            "employeeId": owner_id,
            "tenantId": tenant_id,
            "isOwner": True,
            "createdAt": datetime.utcnow()
        })
        
        # Actualizar tenant con ownerEmployeeId
        await db.tenants.update_one(
            {"_id": tenant_result.inserted_id},
            {"$set": {"ownerEmployeeId": owner_id}}
        )
        tenant_data["ownerEmployeeId"] = owner_id
        # Convertir _id a string para el modelo
        tenant_data["id"] = str(tenant_result.inserted_id)
        tenant_data["_id"] = str(tenant_data["_id"])
        
        # CREAR SERVICIOS DEFAULT PARA EL TENANT
        from app.models.service import ServiceType
        from datetime import timedelta
        
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
            await db.services.insert_one(service_data)
        
        return TenantResponse(**tenant_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.post("/login", response_model=TenantLoginResponse)
async def login_tenant(data: TenantLoginRequest):
    db = get_database()
    """Login tenant by username + password — users es la fuente única de credenciales"""
    login_query = data.email.strip().lower()
    
    # Resolver tenantId desde businessCode (slug) si se envió
    resolved_tenant_id = data.tenantId
    if data.businessCode and not resolved_tenant_id:
        tenant_by_code = await db.tenants.find_one({"businessCode": data.businessCode.strip().lower()})
        if tenant_by_code:
            resolved_tenant_id = tenant_by_code["tenantId"]
    
    if resolved_tenant_id:
        # ===== LOGIN SCOPEADO (con businessCode o tenantId) =====
        # Buscar SOLO dentro del tenant resuelto — nunca global
        user = await db.users.find_one({"username": login_query, "tenantId": resolved_tenant_id})
        
        if user:
            # Verificar contraseña contra users.password_hash
            if not verify_password(data.password, user["password_hash"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas"
                )
            
            # Obtener perfil del employee (employees es solo perfil, sin password)
            employee_id = user.get("employeeId")
            if not employee_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario sin perfil de empleado"
                )
            
            employee = await db.employees.find_one({
                "_id": ObjectId(employee_id),
                "tenantId": resolved_tenant_id,
            })
            if not employee:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Perfil de empleado no encontrado"
                )
            
            # Verificar si la cuenta está INACTIVA
            if employee.get("status") == "INACTIVE":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tu cuenta está INACTIVA. Contacta al administrador."
                )
            
            # Buscar tenant
            tenant = await db.tenants.find_one({"tenantId": resolved_tenant_id})
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Tenant no encontrado"
                )
        else:
            # Usuario no encontrado en users → podría ser demo antiguo (solo tenant.password)
            tenant = await db.tenants.find_one({"tenantId": resolved_tenant_id})
            if not tenant or not tenant.get("isDemo") or "password" not in tenant:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas"
                )
            
            if not verify_password(data.password, tenant["password"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas"
                )
            
            # Crear employee temporal para la respuesta del demo
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
        # ===== SIN SCOPE — SOLO backward compatibility para demos =====
        tenant = await db.tenants.find_one({
            "$or": [
                {"email": login_query},
                {"email": data.email}
            ]
        })
        if not tenant or "password" not in tenant or not tenant.get("isDemo"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas"
            )
        
        if not verify_password(data.password, tenant["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas"
            )
        
        # Crear employee temporal para la respuesta del demo
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
    
    # Auto-cleanup para cuentas demo: borra datos creados en sesiones anteriores
    if tenant.get("isDemo", False):
        collections_to_clean = [
            Collections.SALES,
            Collections.CLIENTS,
            Collections.INVOICES,
            Collections.PRODUCTS,
            Collections.ATTENDANCE,
        ]
        for collection_name in collections_to_clean:
            await db[collection_name].delete_many({
                "tenantId": tenant["tenantId"],
                "isSeed": {"$ne": True},
            })
    
    # Crear token JWT — sub es el username del user (o email del tenant legacy)
    token_data = {
        "sub": user["username"] if user else employee.get("email", ""),
        "role": employee["role"],
        "tenantId": tenant["tenantId"],
        "plan": tenant["plan"],
        "employeeId": str(employee["_id"]),
        "isOwner": employee.get("isOwner", False),
    }
    access_token = create_access_token(token_data)
    
    # Serializar tenant y agregar datos del owner desde employee
    tenant_response = serialize_tenant(tenant)
    tenant_response["ownerFirstName"] = employee.get("firstName", "")
    tenant_response["ownerLastName"] = employee.get("lastName", "")
    tenant_response["ownerUsername"] = employee.get("username", "")
    
    return TenantLoginResponse(
        accessToken=access_token,
        tenant=TenantResponse(**tenant_response)
    )


# Recuperación de contraseña
@router.post("/forgot-password")
async def forgot_password(data: PasswordResetRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Solicitar recuperación de contraseña por email — requiere businessCode o tenantId"""
    # SEGURIDAD: exigir businessCode o tenantId para evitar ambigüedad entre tenants
    if not data.businessCode and not data.tenantId:
        # No revelar si el usuario existe ni si el scope es válido
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}
    
    # Resolver tenantId desde businessCode si se envió
    resolved_tenant_id = data.tenantId
    if data.businessCode and not resolved_tenant_id:
        tenant_by_code = await db.tenants.find_one({"businessCode": data.businessCode.strip().lower()})
        if tenant_by_code:
            resolved_tenant_id = tenant_by_code["tenantId"]
    
    if not resolved_tenant_id:
        # No se pudo resolver tenant — responder genérico sin revelar info
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}
    
    # Buscar en users (fuente única de credenciales) por username + tenantId
    user_query = {"username": data.email.strip().lower(), "tenantId": resolved_tenant_id}
    user = await db.users.find_one(user_query)
    if not user:
        # Por seguridad, no revelar si el usuario existe
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}
    
    # Generar token temporal (15 minutos)
    reset_token = create_access_token({
        "sub": user["username"],
        "type": "password_reset",
        "tenantId": user.get("tenantId"),
        "employeeId": user.get("employeeId"),
    }, expires_delta=timedelta(minutes=15))
    
    # Aquí enviarías el email con el token
    # NOTA: En producción, enviar por email real — no devolver el token
    
    return {
        "message": "Si el correo existe, recibirás un enlace de recuperación",
    }


@router.post("/reset-password")
async def reset_password(data: PasswordResetConfirm, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Cambiar contraseña con token de recuperación — usando users.password_hash"""
    try:
        # Decodificar token con JWT_SECRET_KEY
        payload = jwt.decode(data.token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token inválido"
            )
        
        employee_id = payload.get("employeeId")
        tenant_id = payload.get("tenantId")
        
        # Buscar usuario en users por employeeId
        user = await db.users.find_one({
            "employeeId": employee_id,
            "tenantId": tenant_id
        })
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # Validar que no sea owner (debe cambiar desde su perfil)
        if user.get("isOwner", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Los owners deben cambiar contraseña desde su perfil"
            )
        
        # Actualizar password_hash en users (único lugar)
        new_password_hash = get_password_hash(data.newPassword)
        await db.users.update_one(
            {"employeeId": employee_id, "tenantId": tenant_id},
            {"$set": {"password_hash": new_password_hash}}
        )
        
        return {"message": "Contraseña actualizada correctamente"}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado"
        )


@router.get("/me", response_model=TenantResponse)
async def get_current_tenant(current_user: UserResponse = Depends(get_current_user)):
    # SEGURIDAD: Obtener tenant desde el token, no desde parámetro
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
    
    return TenantResponse(**serialize_tenant(tenant))


@router.put("/me", response_model=TenantResponse)
async def update_current_tenant(data: TenantUpdate, current_user: UserResponse = Depends(get_current_user)):
    # SEGURIDAD: Actualizar tenant desde el token, no desde parámetro
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
    # SEGURIDAD: usar tenantId del token, no de parámetros
    # SEGURIDAD: solo owners pueden renovar
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
    
    # Calcular nueva fecha de vencimiento (1 mes)
    new_end_date = datetime.utcnow() + timedelta(days=30)
    
    update_data = {
        "subscriptionStatus": SubscriptionStatus.ACTIVE,
        "subscriptionEndDate": new_end_date,
        "updatedAt": datetime.utcnow(),
    }
    
    if data.plan:
        update_data["plan"] = data.plan
    
    await db.tenants.update_one(
        {"tenantId": tenant_id},
        {"$set": update_data}
    )
    
    tenant = await db.tenants.find_one({"tenantId": tenant_id})
    return TenantResponse(**serialize_tenant(tenant))


@router.get("/plans")
async def get_plans():
    # Obtener planes disponibles
    """Get available subscription plans"""
    return {
        "plans": [
            {
                "id": "BASIC",
                "name": "Basic",
                "price": 20,
                "features": [
                    "Clientes",
                    "Membresías",
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
                    "Membresías",
                    "Productos",
                    "POS/Ventas",
                    "Asistencia",
                    "Empleados (CRUD)",
                    "Reportes Financieros",
                    "Configuración Completa"
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
            detail="No se encontró el ID del owner"
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
    
    # También actualizar el usuario en la colección users (fuente única de credenciales)
    user_update = {}
    if "username" in update_dict:
        user_update["username"] = update_dict["username"].lower()
    if "password" in update_dict and update_dict["password"]:
        user_update["password_hash"] = get_password_hash(update_dict["password"])
    
    if not final_update and not user_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionaron campos válidos para actualizar"
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
            detail="No se encontró el ID del owner"
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
    # Extrae el tenant del token JWT
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
                detail="Token inválido"
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
            detail="Token inválido"
        )


async def initialize_tenant_demo():
    # SEGURIDAD: Solo crear demo si NO existe - evita duplicados
    db = get_database()
    """Create demo tenant if not exists"""
    from app.models.tenant import SubscriptionPlan, SubscriptionStatus
    from app.models.service import ServiceType
    
    # Demo BASIC - buscar por tenantId, no por email
    existing_basic = await db.tenants.find_one({"tenantId": "demo-basic-001"})
    if not existing_basic:
        demo_basic = {
            "tenantId": "demo-basic-001",
            "businessCode": "demo-basic",
            "email": "demo-basic@gmail.com",
            "password": get_password_hash("demoBasic123"),
            "businessName": "Gimnasio Demo Basic",
            "businessPhone": "",
            "businessAddress": "",
            "businessRuc": "",
            "plan": SubscriptionPlan.BASIC,
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "subscriptionEndDate": None,
            "taxRate": 12.0,
            "currency": "USD",
            "openingHour": "06:00",
            "closingHour": "22:00",
            "wsspReminderDays": 3,
            "wsspEnabled": False,
            "isDemo": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await db.tenants.insert_one(demo_basic)
        
        # Crear servicios default para demo-basic
        await create_default_services("demo-basic-001")
    else:
        # Migrar tenants demo existentes: agregar isDemo y businessCode si faltan
        ops = {}
        if not existing_basic.get("isDemo"):
            ops["isDemo"] = True
        if not existing_basic.get("businessCode"):
            ops["businessCode"] = "demo-basic"
        if ops:
            await db.tenants.update_one(
                {"tenantId": "demo-basic-001"},
                {"$set": ops}
            )
    
    # Crear/actualizar servicios default (idempotente: solo crea si no existe)
    await create_default_services("demo-basic-001")
    
    # Seed data demo-basic (idempotente: solo crea si no existe)
    await seed_demo_data("demo-basic-001")
    
    # Demo PRO - buscar por tenantId
    existing_pro = await db.tenants.find_one({"tenantId": "demo-pro-001"})
    if not existing_pro:
        demo_pro = {
            "tenantId": "demo-pro-001",
            "businessCode": "demo-premium",
            "email": "demo-pro@gmail.com",
            "password": get_password_hash("demoPro123"),
            "businessName": "Gimnasio Demo Pro",
            "businessPhone": "",
            "businessAddress": "",
            "businessRuc": "",
            "plan": SubscriptionPlan.PREMIUM,
            "subscriptionStatus": SubscriptionStatus.ACTIVE,
            "subscriptionEndDate": None,
            "taxRate": 12.0,
            "currency": "USD",
            "openingHour": "06:00",
            "closingHour": "22:00",
            "wsspReminderDays": 3,
            "wsspEnabled": False,
            "isDemo": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await db.tenants.insert_one(demo_pro)
        
        # Crear servicios default para demo-pro
        await create_default_services("demo-pro-001")
    else:
        # Migrar tenants demo existentes: agregar isDemo y businessCode si faltan
        ops = {}
        if not existing_pro.get("isDemo"):
            ops["isDemo"] = True
        if not existing_pro.get("businessCode"):
            ops["businessCode"] = "demo-premium"
        if ops:
            await db.tenants.update_one(
                {"tenantId": "demo-pro-001"},
                {"$set": ops}
            )
    
    # Crear/actualizar servicios default (idempotente: solo crea si no existe)
    await create_default_services("demo-pro-001")
    
    # Seed data demo-pro (idempotente: solo crea si no existe)
    await seed_demo_data("demo-pro-001")


async def create_default_services(tenant_id: str):
    """Crea los servicios default para un tenant"""
    from app.models.service import ServiceType
    db = get_database()
    
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
            "isSeed": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        },
        {
            "tenantId": tenant_id,
            "name": "Día de Prueba",
            "description": "Acceso de prueba por un día",
            "price": 2.00,
            "duration": 1,
            "durationUnit": "days",
            "type": ServiceType.DAILY.value,
            "isActive": True,
            "isSeed": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        },
        {
            "tenantId": tenant_id,
            "name": "Quincenal",
            "description": "Membresía quincenal",
            "price": 18.00,
            "duration": 15,
            "durationUnit": "days",
            "type": ServiceType.MEMBERSHIP.value,
            "isActive": True,
            "isSeed": True,
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
            "isSeed": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        },
    ]
    
    for service_data in default_services:
        # Solo crear si no existen servicios seed
        existing = await db.services.find_one({"tenantId": tenant_id, "name": service_data["name"]})
        if not existing:
            await db.services.insert_one(service_data)


async def seed_demo_data(tenant_id: str):
    """Crea datos semilla fijos para tenants demo.
    Estos datos tienen isSeed=True y NO son eliminados por el cleanup.
    Es IDEMPOTENTE: si ya existen productos seed para este tenant, no hace nada.
    """
    db = get_database()
    from app.models.service import ServiceType
    
    # Verificar si ya existen datos seed para este tenant
    existing_seed = await db.products.find_one({"tenantId": tenant_id, "isSeed": True})
    if existing_seed:
        return
    
    # ============================================================
    # 1. PRODUCTOS (10 con precios variados)
    # ============================================================
    products_data = [
        {"code": "BAR001", "name": "Barra Proteica", "description": "Barra de proteína 30g", "category": "Nutrición", "unitPrice": 2.50, "stock": 50, "minStock": 10},
        {"code": "BEB001", "name": "Bebida Energética", "description": "Bebida isotónica 500ml", "category": "Nutrición", "unitPrice": 3.00, "stock": 40, "minStock": 10},
        {"code": "TOA001", "name": "Toalla Deportiva", "description": "Toalla microfibra 60x30cm", "category": "Accesorios", "unitPrice": 15.00, "stock": 20, "minStock": 5},
        {"code": "SHA001", "name": "Shaker", "description": "Shaker 600ml con mezclador", "category": "Accesorios", "unitPrice": 8.00, "stock": 30, "minStock": 5},
        {"code": "CUE001", "name": "Cuerda para Saltar", "description": "Cuerda ajustable con rodamientos", "category": "Equipamiento", "unitPrice": 12.00, "stock": 15, "minStock": 3},
        {"code": "BAN001", "name": "Bandas de Resistencia", "description": "Set de 5 bandas de diferente intensidad", "category": "Equipamiento", "unitPrice": 20.00, "stock": 15, "minStock": 3},
        {"code": "GUA001", "name": "Guantes de Gimnasio", "description": "Guantes con soporte de muñeca", "category": "Accesorios", "unitPrice": 25.00, "stock": 12, "minStock": 3},
        {"code": "MAT001", "name": "Mat de Yoga", "description": "Mat antideslizante 6mm", "category": "Equipamiento", "unitPrice": 35.00, "stock": 10, "minStock": 2},
        {"code": "BOL001", "name": "Bolso Deportivo", "description": "Bolso impermeable 40L", "category": "Accesorios", "unitPrice": 45.00, "stock": 8, "minStock": 2},
        {"code": "SUP001", "name": "Pack Suplementos", "description": "Combo proteína + creatina + BCAA", "category": "Nutrición", "unitPrice": 60.00, "stock": 5, "minStock": 1},
    ]
    
    product_ids = {}
    for p in products_data:
        doc = {
            **p,
            "tenantId": tenant_id,
            "taxRate": 0.0,
            "isSeed": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        result = await db.products.insert_one(doc)
        product_ids[p["code"]] = str(result.inserted_id)
    
    # ============================================================
    # 2. CLIENTES (2 recién registrados sin membresía + 2 activos)
    # ============================================================
    clients_data = [
        {
            "documentType": "CEDULA", "documentNumber": "0000000000",
            "firstName": "Carlos", "lastName": "López",
            "phone": None, "email": None, "address": None,
            "membership": "Por registrar", "membershipStatus": "NONE",
            "notes": "Cliente recién registrado, sin membresía asignada",
        },
        {
            "documentType": "CEDULA", "documentNumber": "0000000001",
            "firstName": "Ana", "lastName": "Martínez",
            "phone": None, "email": None, "address": None,
            "membership": "Por registrar", "membershipStatus": "NONE",
            "notes": "Cliente recién registrado, sin membresía asignada",
        },
        {
            "documentType": "CEDULA", "documentNumber": "1234567890",
            "firstName": "Juan", "lastName": "Pérez",
            "phone": "0991234567", "email": "juan.perez@email.com",
            "address": "Av. Principal 123",
            "membership": "Mensual", "membershipStatus": "ACTIVE",
            "membershipStartDate": datetime.utcnow(),
            "membershipEndDate": datetime(2026, 6, 9),
        },
        {
            "documentType": "CEDULA", "documentNumber": "0987654321",
            "firstName": "María", "lastName": "García",
            "phone": "0997654321", "email": "maria.garcia@email.com",
            "address": "Calle Secundaria 456",
            "membership": "Pago Diario", "membershipStatus": "ACTIVE",
            "membershipStartDate": datetime.utcnow(),
            "membershipEndDate": datetime.utcnow() + timedelta(days=1),
        },
    ]
    
    client_ids = {}
    for c in clients_data:
        doc = {
            **c,
            "tenantId": tenant_id,
            "fingerPrint": False,
            "emergencyContact": None,
            "emergencyPhone": None,
            "notes": None,
            "isSeed": True,
            "createdAt": datetime.utcnow(),
        }
        result = await db.clients.insert_one(doc)
        client_ids[c["firstName"]] = str(result.inserted_id)
    
    # ============================================================
    # 3. SERVICIOS (referencias para ventas)
    # ============================================================
    daily_service = await db.services.find_one({"tenantId": tenant_id, "name": "Pago Diario"})
    monthly_service = await db.services.find_one({"tenantId": tenant_id, "name": "Mensual"})
    daily_service_id = str(daily_service["_id"]) if daily_service else None
    monthly_service_id = str(monthly_service["_id"]) if monthly_service else None
    
    # ============================================================
    # 4. VENTAS - Historial para clientes activos
    # ============================================================
    sales_seed = [
        # Juan Pérez: Mensual ($30) + Barra Proteica ($2.50)
        {
            "items": [
                {"productName": "Mensual", "description": "Membresía mensual", "quantity": 1, "unitPrice": 30.00, "subtotal": 30.00, "source": "MEMBERSHIP", "serviceId": monthly_service_id},
                {"productName": "Barra Proteica", "description": "", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50, "source": "PRODUCT", "productId": product_ids.get("BAR001")},
            ],
            "subtotal": 32.50, "total": 32.50,
            "clientName": "Juan Pérez", "clientId": client_ids.get("Juan"),
            "cashAmount": 32.50, "paymentMethod": "CASH",
        },
        # María García: Pago Diario ($2.50) + Bebida Energética ($3.00)
        {
            "items": [
                {"productName": "Pago Diario", "description": "Acceso por un día", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50, "source": "DAILY", "serviceId": daily_service_id},
                {"productName": "Bebida Energética", "description": "", "quantity": 1, "unitPrice": 3.00, "subtotal": 3.00, "source": "PRODUCT", "productId": product_ids.get("BEB001")},
            ],
            "subtotal": 5.50, "total": 5.50,
            "clientName": "María García", "clientId": client_ids.get("María"),
            "cashAmount": 5.50, "paymentMethod": "CASH",
        },
        # 2 membresías diarias extra
        {
            "items": [
                {"productName": "Pago Diario", "description": "Acceso por un día", "quantity": 2, "unitPrice": 2.50, "subtotal": 5.00, "source": "DAILY", "serviceId": daily_service_id},
            ],
            "subtotal": 5.00, "total": 5.00,
            "clientName": "Venta Directa", "cashAmount": 5.00, "paymentMethod": "CASH",
        },
        # 2 ventas de productos extra
        {
            "items": [
                {"productName": "Toalla Deportiva", "description": "", "quantity": 1, "unitPrice": 15.00, "subtotal": 15.00, "source": "PRODUCT", "productId": product_ids.get("TOA001")},
            ],
            "subtotal": 15.00, "total": 15.00,
            "clientName": "Venta Directa", "cashAmount": 15.00, "paymentMethod": "CASH",
        },
        {
            "items": [
                {"productName": "Shaker", "description": "", "quantity": 2, "unitPrice": 8.00, "subtotal": 16.00, "source": "PRODUCT", "productId": product_ids.get("SHA001")},
            ],
            "subtotal": 16.00, "total": 16.00,
            "clientName": "Venta Directa", "cashAmount": 16.00, "paymentMethod": "CASH",
        },
        # Renovación mensual pendiente (para Juan Pérez, el cliente mensual activo)
        {
            "items": [
                {"productName": "Mensual", "description": "Renovación mensual - Pendiente", "quantity": 1, "unitPrice": 30.00, "subtotal": 30.00, "source": "MEMBERSHIP", "serviceId": monthly_service_id},
            ],
            "subtotal": 30.00, "total": 30.00,
            "clientName": "Juan Pérez",
            "clientId": client_ids.get("Juan"),
            "cashAmount": 0.0, "paymentMethod": "TRANSFER", "paymentStatus": "pending",
            "voucherCode": "PEND-001",
        },
    ]
    
    sale_ids = []
    for i, s in enumerate(sales_seed):
        doc = {
            **s,
            "tenantId": tenant_id,
            "tax": 0.0,
            "paymentStatus": s.get("paymentStatus", "verified"),
            "transferAmount": 0.0,
            "clientFirstName": None, "clientLastName": None,
            "clientDocument": None, "clientEmail": None,
            "clientPhone": None, "clientAddress": None,
            "generateInvoice": False, "invoiceEmail": None,
            "createdBy": "demo-basic@gmail.com",
            "createdAt": datetime.utcnow() - timedelta(hours=i * 2),
            "isSeed": True,
        }
        if not doc.get("paymentStatus"):
            doc["paymentStatus"] = "verified"
        result = await db.sales.insert_one(doc)
        sale_ids.append(str(result.inserted_id))
    
    # ============================================================
    # 5. FACTURAS
    # ============================================================
    # Buscar datos del tenant para datos de negocio
    tenant_doc = await db.tenants.find_one({"tenantId": tenant_id})
    business = {
        "name": tenant_doc.get("businessName", "Gimnasio Demo"),
        "ruc": tenant_doc.get("businessRuc", "9999999999001"),
        "address": tenant_doc.get("businessAddress", "Dirección del gimnasio"),
        "phone": tenant_doc.get("businessPhone", "0999999999"),
        "email": tenant_doc.get("email", "demo@gimnasio.com"),
    }
    
    invoices_seed = [
        # Factura Juan Pérez
        {
            "type": "MEMBERSHIP",
            "client": {"documentNumber": "1234567890", "firstName": "Juan", "lastName": "Pérez", "email": "juan.perez@email.com"},
            "items": [
                {"name": "Mensual", "quantity": 1, "unitPrice": 30.00, "subtotal": 30.00},
                {"name": "Barra Proteica", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50},
            ],
            "totals": {"subtotal": 32.50, "total": 32.50},
            "payment": {"method": "CASH", "cashAmount": 32.50, "paid": 32.50},
        },
        # Factura María García
        {
            "type": "MEMBERSHIP",
            "client": {"documentNumber": "0987654321", "firstName": "María", "lastName": "García", "email": "maria.garcia@email.com"},
            "items": [
                {"name": "Pago Diario", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50},
                {"name": "Bebida Energética", "quantity": 1, "unitPrice": 3.00, "subtotal": 3.00},
            ],
            "totals": {"subtotal": 5.50, "total": 5.50},
            "payment": {"method": "CASH", "cashAmount": 5.50, "paid": 5.50},
        },
        # Factura de compra de productos
        {
            "type": "PRODUCT",
            "client": {"documentNumber": "9999999999", "firstName": "Proveedor", "lastName": "Mayorista", "email": "proveedor@email.com"},
            "items": [
                {"name": "Barra Proteica", "quantity": 20, "unitPrice": 1.50, "subtotal": 30.00},
                {"name": "Bebida Energética", "quantity": 15, "unitPrice": 2.00, "subtotal": 30.00},
                {"name": "Toalla Deportiva", "quantity": 10, "unitPrice": 8.00, "subtotal": 80.00},
                {"name": "Shaker", "quantity": 10, "unitPrice": 4.00, "subtotal": 40.00},
            ],
            "totals": {"subtotal": 180.00, "total": 180.00},
            "payment": {"method": "TRANSFER", "cashAmount": 0.0, "transferAmount": 180.00, "paid": 180.00, "voucherCode": "FAC-PROV-001"},
        },
    ]
    
    for inv_data in invoices_seed:
        doc = {
            "tenantId": tenant_id,
            "type": inv_data["type"],
            "invoiceNumber": f"DEMO-{inv_data['type'][:4]}-{datetime.now().year}-{len(invoices_seed):06d}",
            "business": business,
            "client": inv_data["client"],
            "items": inv_data["items"],
            "totals": inv_data["totals"],
            "payment": inv_data["payment"],
            "status": "GENERATED",
            "createdBy": "demo-basic@gmail.com",
            "createdAt": datetime.utcnow(),
            "isSeed": True,
        }
        await db.invoices.insert_one(doc)
