# Esquemas Pydantic para Tenants (Gimnasios)
# Relacionado con: routers/tenants.py, database.py
"""Tenant (Gimnasio) Pydantic schemas"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum


class SubscriptionPlan(str, Enum):
    # Planes de suscripción disponibles
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"


class SubscriptionStatus(str, Enum):
    # Estado de suscripción del tenant
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"


def slugify(text: str) -> str:
    """Convierte un texto en un slug URL-friendly.
    Ej: 'Mi Gimnasio' → 'mi-gimnasio', 'El Gym de Juan!' → 'el-gym-de-juan'
    """
    import re
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)  # sacar caracteres especiales
    text = re.sub(r'[-\s]+', '-', text)    # espacios/guiones múltiples → un guión
    return text.strip('-')


class TenantBase(BaseModel):
    # Datos base del tenant (requeridos al registro)
    email: EmailStr  # Email con validación automática
    businessName: str = Field(..., min_length=2, max_length=100)
    businessCode: Optional[str] = None  # Slug generado del nombre, para login multi-tenant
    businessPhone: Optional[str] = None
    businessAddress: Optional[str] = None
    businessRuc: Optional[str] = None
    # Referencia al owner principal (employee)
    ownerEmployeeId: Optional[str] = None


class TenantCreate(TenantBase):
    # Datos para crear tenant nuevo (registro)
    # Incluye datos del owner principal
    password: str = Field(..., min_length=6, max_length=100)
    plan: SubscriptionPlan = SubscriptionPlan.BASIC
    # Datos del owner
    ownerFirstName: str  # Nombre del owner
    ownerLastName: str   # Apellido del owner


class TenantUpdate(BaseModel):
    # Datos para actualizar tenant
    businessName: Optional[str] = Field(None, min_length=2, max_length=100)
    businessPhone: Optional[str] = None
    businessAddress: Optional[str] = None
    businessRuc: Optional[str] = None
    plan: Optional[SubscriptionPlan] = None
    subscriptionStatus: Optional[SubscriptionStatus] = None
    subscriptionEndDate: Optional[datetime] = None


class TenantResponse(TenantBase):
    # Respuesta con todos los datos del tenant
    id: str
    tenantId: str
    plan: SubscriptionPlan = SubscriptionPlan.BASIC
    isDemo: bool = False
    subscriptionStatus: SubscriptionStatus = SubscriptionStatus.PENDING
    subscriptionEndDate: Optional[datetime] = None
    taxRate: float = 12.0
    currency: str = "USD"
    openingHour: str = "06:00"
    closingHour: str = "22:00"
    wsspReminderDays: int = 3
    wsspEnabled: bool = False
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    # Datos del owner para el frontend
    ownerFirstName: Optional[str] = None
    ownerLastName: Optional[str] = None
    ownerUsername: Optional[str] = None

    class Config:
        populate_by_name = True


class TenantLoginRequest(BaseModel):
    # Solicitud de login del tenant
    # Enviar businessCode o tenantId scopea la búsqueda (multi-tenant real)
    email: str
    password: str
    tenantId: Optional[str] = None
    businessCode: Optional[str] = None  # Slug amigable del nombre del negocio


class PasswordResetRequest(BaseModel):
    email: str
    tenantId: Optional[str] = None
    businessCode: Optional[str] = None


class PasswordResetConfirm(BaseModel):
    token: str
    newPassword: str


class TenantLoginResponse(BaseModel):
    # Respuesta de login exitoso
    accessToken: str
    tokenType: str = "bearer"
    tenant: TenantResponse