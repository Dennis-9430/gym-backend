# Esquemas Pydantic para servicios/membresías
# Relacionado con: routers/services.py, database.py
"""Service (Membership) Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ServiceBase(BaseModel):
    # Datos base del servicio
    # Relacionado con: routers/services.py, frontend
    name: str
    description: str = ""
    price: float = 0.0
    duration: int = 30
    durationUnit: str = "days"
    isActive: bool = True


class ServiceCreate(ServiceBase):
    # Datos para crear servicio
    # Relacionado con: routers/services.py (create_service)
    pass


class ServiceUpdate(BaseModel):
    # Datos para actualizar servicio
    # Relacionado con: routers/services.py (update_service)
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    duration: Optional[int] = None
    durationUnit: Optional[str] = None
    isActive: Optional[bool] = None


class ServiceResponse(ServiceBase):
    # Respuesta con todos los datos del servicio
    # Relacionado con: routers/services.py (get_service)
    id: str = Field(..., alias="_id")
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ServiceListResponse(BaseModel):
    # Lista de servicios con paginación
    # Relacionado con: routers/services.py (list_services)
    services: list[ServiceResponse]
    total: int
