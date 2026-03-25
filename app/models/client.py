"""Client Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    CEDULA = "CEDULA"
    PASAPORTE = "PASAPORTE"
    RUC = "RUC"


class MembershipStatus(str, Enum):
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
    membership: str = "Por registrar"
    membershipStatus: MembershipStatus = MembershipStatus.NONE
    fingerPrint: bool = False


class ClientUpdate(BaseModel):
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
    id: int = Field(..., alias="_id")
    membership: str = "Por registrar"
    membershipStatus: MembershipStatus = MembershipStatus.NONE
    membershipStartDate: Optional[datetime] = None
    membershipEndDate: Optional[datetime] = None
    fingerPrint: bool = False
    createdAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ClientListResponse(BaseModel):
    clients: list[ClientResponse]
    total: int