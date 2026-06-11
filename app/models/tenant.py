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
    PENDING_PAYMENT = "PENDING_PAYMENT"
    SUSPENDED = "SUSPENDED"


class PaymentMethod(str, Enum):
    CASH = "CASH"
    TRANSFER = "TRANSFER"
    CARD = "CARD"
    OTHER = "OTHER"
    MOCK = "MOCK"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    REJECTED = "REJECTED"
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
    isDemo: bool = Field(default=False)
    # Datos del owner
    ownerFirstName: str  # Nombre del owner
    ownerLastName: str   # Apellido del owner
    # Payment fields (opcional — si no se envía, queda PENDING_PAYMENT)
    paymentMethod: Optional[PaymentMethod] = None
    cardToken: Optional[str] = None
    transferReference: Optional[str] = None
    receiptUrl: Optional[str] = None
    paymentMonths: int = 1


class TenantUpdate(BaseModel):
    # Datos para actualizar tenant
    businessName: Optional[str] = Field(None, min_length=2, max_length=100)
    businessPhone: Optional[str] = None
    businessAddress: Optional[str] = None
    businessRuc: Optional[str] = None
    plan: Optional[SubscriptionPlan] = None
    subscriptionStatus: Optional[SubscriptionStatus] = None
    subscriptionEndDate: Optional[datetime] = None
    biometricEnabled: Optional[bool] = None  # Super admin habilita huella biométrica


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
    biometricEnabled: bool = False  # Super admin toggle para huella biométrica
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


class ManualPaymentCreate(BaseModel):
    plan: SubscriptionPlan
    months: int = Field(ge=1, le=24)
    amount: float = Field(gt=0)
    currency: str = "USD"
    method: PaymentMethod
    reference: Optional[str] = None
    notes: Optional[str] = None


class ManualPaymentResponse(BaseModel):
    id: str
    tenantId: str
    plan: SubscriptionPlan
    months: int
    amount: float
    currency: str
    method: PaymentMethod
    reference: Optional[str] = None
    notes: Optional[str] = None
    registeredBy: Optional[str] = None
    subscriptionStartDate: Optional[datetime] = None
    subscriptionEndDate: Optional[datetime] = None
    status: Optional[str] = None
    source: Optional[str] = None
    receiptUrl: Optional[str] = None
    createdAt: Optional[datetime] = None


class RegistrationPayment(BaseModel):
    """Payment data submitted during tenant registration"""
    method: PaymentMethod
    cardToken: Optional[str] = None          # PayPhone token (stub for now)
    transferReference: Optional[str] = None   # Optional reference/note for transfer
    receiptUrl: Optional[str] = None          # Uploaded receipt URL
    months: int = 1                           # Default: 1 month


class PendingPaymentResponse(BaseModel):
    """Pending transfer payment visible to super admin"""
    id: str
    tenantId: str
    tenantName: str
    tenantEmail: str
    plan: SubscriptionPlan
    amount: float
    currency: str
    method: PaymentMethod
    reference: Optional[str] = None
    receiptUrl: Optional[str] = None
    status: PaymentStatus
    notes: Optional[str] = None
    createdAt: datetime
    updatedAt: Optional[datetime] = None


class ApprovePaymentRequest(BaseModel):
    notes: Optional[str] = None


class RejectPaymentRequest(BaseModel):
    reason: str