"""Employee Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class EmployeeRole(str, Enum):
    """Employee roles"""
    ADMIN = "ADMIN"
    RECEPCIONISTA = "RECEPCIONISTA"
    ENTRENADOR = "ENTRENADOR"


class EmployeeStatus(str, Enum):
    """Employee status"""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class Permission(BaseModel):
    """Permission schema"""
    module: str
    actions: List[str]


class EmployeeBase(BaseModel):
    """Base employee schema"""
    username: str
    documentType: str = "CEDULA"
    documentNumber: str
    firstName: str
    lastName: str
    email: str
    phone: str
    role: EmployeeRole
    status: EmployeeStatus = EmployeeStatus.ACTIVE


class EmployeeCreate(EmployeeBase):
    """Employee creation schema"""
    password: Optional[str] = None


class EmployeeUpdate(BaseModel):
    """Employee update schema"""
    documentType: Optional[str] = None
    documentNumber: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[EmployeeRole] = None
    status: Optional[EmployeeStatus] = None


class EmployeeResponse(EmployeeBase):
    """Employee response schema"""
    id: str = Field(..., alias="_id")
    permissions: List[Permission] = []
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class EmployeeListResponse(BaseModel):
    """Employee list response"""
    employees: List[EmployeeResponse]
    total: int