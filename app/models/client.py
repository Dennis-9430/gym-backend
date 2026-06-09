# Esquemas Pydantic para clientes
# Relacionado con: routers/clients.py, database.py
"""Client Pydantic schemas"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    # Tipos de documento de identidad
    CEDULA = "CEDULA"
    PASAPORTE = "PASAPORTE"
    RUC = "RUC"


class MembershipStatus(str, Enum):
    # Estado de membresía del cliente
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class MembershipType(str, Enum):
    QUINCENAL = "Quincenal"
    MENSUAL = "Mensual"
    TRIMESTRAL = "Trimestral"
    SEMESTRAL = "Semestral"
    ANUAL = "Anual"


class ClientBase(BaseModel):
    # Datos base del cliente (requeridos)
    tenantId: str = ""
    documentType: DocumentType = DocumentType.CEDULA
    documentNumber: str = Field(..., min_length=4, max_length=20)
    firstName: str = Field(..., min_length=1, max_length=50)
    lastName: str = Field(..., min_length=1, max_length=50)
    phone: Optional[str] = Field(None, min_length=8, max_length=20)
    email: Optional[EmailStr] = None
    address: Optional[str] = Field(None, max_length=200)
    emergencyContact: Optional[str] = Field(None, max_length=100)
    emergencyPhone: Optional[str] = Field(None, min_length=8, max_length=20)
    notes: Optional[str] = Field(None, max_length=500)


class ClientCreate(ClientBase):
    # Datos para crear cliente nuevo
    # Relacionado con: routers/clients.py (create_client)
    membership: str = "Por registrar"
    membershipStatus: MembershipStatus = MembershipStatus.NONE
    fingerPrint: bool = False


class ClientUpdate(BaseModel):
    # Datos para actualizar cliente
    # Relacionado con: routers/clients.py (update_client)
    client_id: str = ""
    documentType: Optional[DocumentType] = None
    documentNumber: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    emergencyContact: Optional[str] = None
    emergencyPhone: Optional[str] = None
    notes: Optional[str] = None
    membership: Optional[str] = None
    membershipStatus: Optional[MembershipStatus] = None
    membershipStartDate: Optional[datetime] = None
    membershipEndDate: Optional[datetime] = None
    fingerPrint: Optional[bool] = None


class ClientResponse(ClientBase):
    # Respuesta con todos los datos del cliente
    # Relacionado con: routers/clients.py (get_client)
    id: str
    membership: str = "Por registrar"
    membershipStatus: MembershipStatus = MembershipStatus.NONE
    membershipStartDate: Optional[datetime] = None
    membershipEndDate: Optional[datetime] = None
    fingerPrint: bool = False
    createdAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ClientListResponse(BaseModel):
    # Lista de clientes con paginación
    # Relacionado con: routers/clients.py (list_clients)
    clients: list[ClientResponse]
    total: int
    page: int = 1
    limit: int = 50