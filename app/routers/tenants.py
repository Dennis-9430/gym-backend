# Router para Tenants (Gimnasios)
# Relacionado con: models/tenant.py, database.py, main.py
"""Tenant (Gym) API router"""
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Depends, status
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_database
from app.config import settings
from app.models.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantLoginRequest,
    TenantLoginResponse,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.auth.utils import verify_password, get_password_hash, create_access_token
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


def serialize_tenant(doc: dict) -> dict:
    # Convierte documento de MongoDB a respuesta
    """Serialize MongoDB document to response"""
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.post("/register", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(data: TenantCreate):
    # Registro de nuevo tenant (gimnasio)
    db = get_database()
    # Registro de nuevo tenant (gimnasio)
    """Register a new gym tenant"""
    # Verificar si el email ya existe
    existing = await db.tenants.find_one({"email": data.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya está registrado"
        )
    
    # Crear el tenant
    tenant_data = {
        "tenantId": str(uuid4()),
        "email": data.email,
        "password": get_password_hash(data.password),
        "businessName": data.businessName,
        "businessPhone": data.businessPhone,
        "businessAddress": data.businessAddress or "",
        "businessRuc": data.businessRuc or "",
        "plan": data.plan,
        "subscriptionStatus": SubscriptionStatus.PENDING,
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
    
    result = await db.tenants.insert_one(tenant_data)
    tenant_data["_id"] = result.inserted_id
    
    return TenantResponse(**tenant_data)


@router.post("/login", response_model=TenantLoginResponse)
async def login_tenant(data: TenantLoginRequest):
    db = get_database()
    # Login de tenant por email y contraseña
    """Login tenant with email and password"""
    # Buscar tenant por email
    tenant = await db.tenants.find_one({"email": data.email})
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )
    
    # Verificar contraseña
    if not verify_password(data.password, tenant["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )
    
    # Crear token JWT
    token_data = {
        "sub": tenant["email"],
        "tenantId": tenant["tenantId"],
        "plan": tenant["plan"],
    }
    access_token = create_access_token(token_data)
    
    return TenantLoginResponse(
        accessToken=access_token,
        tenant=TenantResponse(**serialize_tenant(tenant))
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
    
    tenant = await db.tenants.find_one({"tenantId": tenantId})
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
        print("✅ Demo BASIC created: demo-basic-001")
    
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
        print("✅ Demo PRO created: demo-pro-001")