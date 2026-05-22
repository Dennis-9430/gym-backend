# Esquemas Pydantic para empleados
# Relacionado con: routers/employees.py, database.py
"""Employee Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class EmployeeRole(str, Enum):
    ADMIN = "ADMIN"
    RECEPCIONISTA = "RECEPCIONISTA"
    GERENTE = "GERENTE"


class EmployeeStatus(str, Enum):
    # Estado del empleado
    # Relacionado con: routers/employees.py
    """Employee status"""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class Permission(BaseModel):
    # Esquema de permisos por módulo
    # Relacionado con: routers/employees.py
    """Permission schema"""
    module: str
    actions: List[str]


class EmployeeBase(BaseModel):
    # Datos base del empleado
    # Relacionado con: routers/employees.py
    """Base employee schema"""
    tenantId: str = ""  # ID del tenant (gimnasio) al que pertenece
    username: str
    documentType: str = "CEDULA"
    documentNumber: str
    firstName: str
    lastName: str
    email: str
    phone: str
    role: EmployeeRole
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    isOwner: bool = False  # Indica si es el owner principal del tenant


class EmployeeCreate(EmployeeBase):
    # Datos para crear empleado
    # Relacionado con: routers/employees.py (create_employee)
    """Employee creation schema"""
    password: Optional[str] = None
    fingerPrint: bool = False


class EmployeeUpdate(BaseModel):
    # Datos para actualizar empleado
    # Relacionado con: routers/employees.py (update_employee)
    """Employee update schema"""
    documentType: Optional[str] = None
    documentNumber: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[EmployeeRole] = None
    status: Optional[EmployeeStatus] = None
    fingerPrint: Optional[bool] = None


class EmployeeResponse(EmployeeBase):
    # Respuesta con todos los datos del empleado
    # Relacionado con: routers/employees.py (get_employee)
    """Employee response schema"""
    id: str
    permissions: List[Permission] = []
    fingerPrint: bool = False
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


# Esquema para crear owner desde register (sin username inicial)
class OwnerCreate(BaseModel):
    # Datos para crear owner durante registro del tenant
    # No requiere username - se configura después
    """Owner creation schema for tenant register"""
    firstName: str
    lastName: str
    email: str
    password: str


class EmployeeListResponse(BaseModel):
    # Lista de empleados con paginación
    # Relacionado con: routers/employees.py (list_employees)
    """Employee list response"""
    employees: List[EmployeeResponse]
    total: int