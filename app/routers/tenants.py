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
        
        # Generar tenantId único
        tenant_id = str(uuid4())
        
        # Datos del tenant
        tenant_data = {
            "tenantId": tenant_id,
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
        
        # Crear el OWNER automáticamente
        owner_data = {
            "tenantId": tenant_id,
            "username": data.email,  # Username inicial = email
            "documentType": "CEDULA",
            "documentNumber": "",
            "firstName": data.ownerFirstName,
            "lastName": data.ownerLastName,
            "email": data.email,  # Mismo email que tenant
            "phone": data.businessPhone or "",
            "role": "ADMIN",
            "status": "ACTIVE",  # Usar status, no isActive
            "isOwner": True,  # Flag de owner
            "password": get_password_hash(data.password),  # Hashear contraseña
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
            "role": "ADMIN",
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
    """Login tenant by email or username + password"""
    # Buscar employee por email o username (SIN filtro de status)
    login_query = data.email.strip().lower()
    employee = await db.employees.find_one({
        "$or": [
            {"email": login_query},
            {"username": login_query}
        ]
    })
    
    # Si no se encuentra employee, buscar en tenants (backward compatibility con demos)
    if not employee:
        tenant = await db.tenants.find_one({
            "$or": [
                {"email": login_query},
                {"email": data.email}
            ]
        })
        if tenant and "password" in tenant:
            # Es un demo/tenant antiguo - verificar contraseña
            if verify_password(data.password, tenant["password"]):
                # Crear employee temporal para el demo
                employee = {
                    "_id": str(tenant.get("_id")),
                    "tenantId": tenant.get("tenantId"),
                    "email": tenant.get("email"),
                    "firstName": tenant.get("businessName", "Admin"),
                    "lastName": "",
                    "role": "ADMIN",
                    "isOwner": True,
                    "status": "ACTIVE",  # Usar status, no isActive
                    "password": tenant.get("password"),  # Para verificar
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas"
            )
    else:
        # Verificar SI la cuenta está INACTIVA antes de verificar contraseña
        if employee.get("status") == "INACTIVE":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu cuenta está INACTIVA. Contacta al administrador."
            )
        
        # Verificar contraseña del employee
        if not verify_password(data.password, employee["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas"
            )
        
        # Buscar tenant del employee
        tenant = await db.tenants.find_one({"tenantId": employee["tenantId"]})
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant no encontrado"
            )
    
    # Verificar subscription activa
    if tenant.get("subscriptionStatus") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Suscripción inactiva. Contacte al administrador."
        )
    
    # Crear token JWT con datos del employee
    token_data = {
        "sub": employee["email"],
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
    """Solicitar recuperación de contraseña por email"""
    # Buscar employee por email
    employee = await db.employees.find_one({"email": data.email})
    if not employee:
        # Por seguridad, no revelar si el email existe
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}
    
    # Buscar tenant para verificar estado
    tenant = await db.tenants.find_one({"tenantId": employee["tenantId"]})
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Generar token temporal (15 minutos)
    reset_token = create_access_token({
        "sub": employee["email"],
        "type": "password_reset",
        "tenantId": tenant["tenantId"],
        "employeeId": str(employee["_id"]),
    }, expires_delta=timedelta(minutes=15))
    
    # Aquí enviarías el email con el token
    # Por ahora, devolvemos el token (en producción usar SMTP)
    # NOTA: En producción, enviar por email real
    
    return {
        "message": "Si el correo existe, recibirás un enlace de recuperación",
        "token": reset_token  # TODO: Enviar por email en producción
    }


@router.post("/reset-password")
async def reset_password(data: PasswordResetConfirm, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Cambiar contraseña con token de recuperación"""
    try:
        # Decodificar token
        payload = jwt.decode(data.token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token inválido"
            )
        
        employee_id = payload.get("employeeId")
        tenant_id = payload.get("tenantId")
        
        # Buscar employee
        employee = await db.employees.find_one({
            "_id": ObjectId(employee_id),
            "tenantId": tenant_id
        })
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # Validar que no sea owner (no puede cambiar password así)
        # El owner debe cambiar desde su perfil
        if employee.get("isOwner", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Los owners deben cambiar contraseña desde su perfil"
            )
        
        # Actualizar contraseña
        new_password_hash = get_password_hash(data.newPassword)
        await db.employees.update_one(
            {"_id": ObjectId(employee_id)},
            {"$set": {"password": new_password_hash, "updatedAt": datetime.utcnow()}}
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
async def renew_subscription(data: TenantUpdate, tenantId: str):
    db = get_database()
    # Renovar suscripción (1 mes por defecto)
    """Renew subscription"""
    tenant = await db.tenants.find_one({"tenantId": tenantId})
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
        {"tenantId": tenantId},
        {"$set": update_data}
    )
    
    tenant = await db.tenants.find_one({"tenantId": tenantId})
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
    
    # Campos permitidos para el owner
    allowed_fields = ["firstName", "lastName", "phone", "address", "documentNumber", "documentType", "notes", "username", "password"]
    final_update = {k: v for k, v in update_dict.items() if k in allowed_fields and v is not None}
    
    if not final_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionaron campos válidos para actualizar"
        )
    
    if "password" in final_update:
        final_update["password"] = get_password_hash(final_update["password"])
    
    # También actualizar el usuario en la colección users
    user_update = {}
    if "username" in final_update:
        user_update["username"] = final_update["username"].lower()
    if "password" in final_update:
        user_update["password_hash"] = final_update["password"]
    
    if user_update:
        await db[Collections.USERS].update_one(
            {"employeeId": owner_employee_id},
            {"$set": user_update}
        )
    
    final_update["updatedAt"] = datetime.utcnow()
    
    await db[Collections.EMPLOYEES].update_one(
        {"_id": ObjectId(owner_employee_id), "tenantId": tenant.tenantId},
        {"$set": final_update}
    )
    
    updated_owner = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(owner_employee_id)})
    
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
    
    # Demo BASIC - buscar por tenantId, no por email
    existing_basic = await db.tenants.find_one({"tenantId": "demo-basic-001"})
    if not existing_basic:
        demo_basic = {
            "tenantId": "demo-basic-001",
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
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await db.tenants.insert_one(demo_basic)
    
    # Demo PRO - buscar por tenantId
    existing_pro = await db.tenants.find_one({"tenantId": "demo-pro-001"})
    if not existing_pro:
        demo_pro = {
            "tenantId": "demo-pro-001",
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
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await db.tenants.insert_one(demo_pro)