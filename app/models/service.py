"""Service (Membership) Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ServiceBase(BaseModel):
    name: str
    description: str = ""
    price: float = 0.0
    duration: int = 30
    durationUnit: str = "days"
    isActive: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    duration: Optional[int] = None
    durationUnit: Optional[str] = None
    isActive: Optional[bool] = None


class ServiceResponse(ServiceBase):
    id: str = Field(..., alias="_id")
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ServiceListResponse(BaseModel):
    services: list[ServiceResponse]
    total: int
