# Esquemas Pydantic para clientes
# Relacionado con: routers/clients.py, database.py
"""Client Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    # Tipos de documento de identidad
    # Relacionado con: routers/clients.py, frontend
    CEDULA = "CEDULA"
    PASAPORTE = "PASAPORTE"
    RUC = "RUC"


class MembershipStatus(str, Enum):
    # Estado de membresía del cliente
    # Relacionado con: routers/clients.py, frontend
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class MembershipType(str, Enum):
    # Tipos de membresía disponibles
    # Relacionado con: routers/clients.py
    QUINCENAL = "Quincenal"
    MENSUAL = "Mensual"
    TRIMESTRAL = "Trimestral"
    SEMESTRAL = "Semestral"
    ANUAL = "Anual"


class ClientBase(BaseModel):
    # Datos base del cliente (requeridos)
    # Relacionado con: routers/clients.py, frontend
    tenantId: str = ""  # ID del tenant (gimnasio) al que pertenece
    documentType: DocumentType = DocumentType.CEDULA
    documentNumber: str
    firstName: str
    lastName: str
    phone: str = ""
    email: str = ""
    address: str = ""
    emergencyContact: str = ""
    emergencyPhone: str = ""
    notes: str = ""


class ClientCreate(ClientBase):
    # Datos para crear cliente nuevo
    # Relacionado con: routers/clients.py (create_client)
    membership: str = "Por registrar"
    membershipStatus: MembershipStatus = MembershipStatus.NONE
    fingerPrint: bool = False


class ClientUpdate(BaseModel):
    # Datos para actualizar cliente
    # Relacionado con: routers/clients.py (update_client)
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
    id: str = Field(..., alias="_id")
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