# Modelos Pydantic para Notificaciones WhatsApp
"""Notification Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class NotificationType(str, Enum):
    """Tipos de notificación"""
    EXPIRY = "expiry"           # Recordatorio de vencimiento
    SCHEDULED = "scheduled"     # Mensaje programado (promoción/festivo)


class NotificationConfigBase(BaseModel):
    """Datos base de configuración"""
    type: NotificationType
    message: str
    scheduledDate: Optional[str] = None  # YYYY-MM-DD
    scheduledTime: Optional[str] = None   # HH:mm
    expiryHour: int = 20                # Hora de envío (default 20:00)
    enabled: bool = True


class NotificationConfigCreate(NotificationConfigBase):
    """Crear configuración"""
    pass


class NotificationConfigUpdate(BaseModel):
    """Actualizar configuración"""
    message: Optional[str] = None
    scheduledDate: Optional[str] = None
    scheduledTime: Optional[str] = None
    expiryHour: Optional[int] = None
    enabled: Optional[bool] = None


class NotificationConfigResponse(NotificationConfigBase):
    """Respuesta de configuración"""
    id: str
    sentToday: bool = False
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class NotificationLogBase(BaseModel):
    """Datos base del log"""
    clientId: str
    type: NotificationType
    message: str
    status: str = "success"  # "success" | "failed"


class NotificationLogResponse(NotificationLogBase):
    """Respuesta del log"""
    id: str
    sentAt: datetime

    class Config:
        populate_by_name = True