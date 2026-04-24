# Esquemas Pydantic para Tenants (Gimnasios)
# Relacionado con: routers/tenants.py, database.py
"""Tenant (Gimnasio) Pydantic schemas"""
from pydantic import BaseModel, Field
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


class TenantBase(BaseModel):
    # Datos base del tenant (requeridos al registro)
    email: str
    businessName: str
    businessPhone: str = ""
    businessAddress: str = ""
    businessRuc: str = ""


class TenantCreate(TenantBase):
    # Datos para crear tenant nuevo (registro)
    password: str
    plan: SubscriptionPlan = SubscriptionPlan.BASIC


class TenantUpdate(BaseModel):
    # Datos para actualizar tenant
    businessName: Optional[str] = None
    businessPhone: Optional[str] = None
    businessAddress: Optional[str] = None
    businessRuc: Optional[str] = None
    plan: Optional[SubscriptionPlan] = None
    subscriptionStatus: Optional[SubscriptionStatus] = None
    subscriptionEndDate: Optional[datetime] = None


class TenantResponse(TenantBase):
    # Respuesta con todos los datos del tenant
    id: str = Field(..., alias="_id")
    tenantId: str
    plan: SubscriptionPlan = SubscriptionPlan.BASIC
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

    class Config:
        populate_by_name = True


class TenantLoginRequest(BaseModel):
    # Solicitud de login del tenant
    email: str
    password: str


class TenantLoginResponse(BaseModel):
    # Respuesta de login exitoso
    accessToken: str
    tokenType: str = "bearer"
    tenant: TenantResponse