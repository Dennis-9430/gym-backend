# Esquemas Pydantic para validación de autenticación
# Relacionado con: auth/router.py, auth/service.py
"""Pydantic schemas for authentication"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    RECEPCIONISTA = "RECEPCIONISTA"


class TokenData(BaseModel):
    # Datos contenidos en el token JWT
    # Relacionado con: auth/utils.py
    """Token payload data"""
    username: Optional[str] = None
    role: Optional[UserRole] = None


class Token(BaseModel):
    # Respuesta del endpoint de login
    # Relacionado con: auth/service.py (create_token)
    """JWT token response"""
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    # Datos para iniciar sesión
    # Relacionado con: auth/router.py (login)
    """Login request payload"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    # Datos públicos del usuario (sin contraseña)
    # Relacionado con: auth/router.py (get_current_user)
    """User response without sensitive data"""
    username: str
    role: UserRole
    employeeId: Optional[str] = None
    tenantId: Optional[str] = None
    isOwner: Optional[bool] = None
    plan: Optional[str] = None
    isInactive: Optional[bool] = None  # Indica si la cuenta está inactiva


class UserCreate(BaseModel):
    # Datos para crear nuevo usuario
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=6, max_length=50)
    role: UserRole
    employeeId: Optional[str] = None


class PasswordChange(BaseModel):
    # Datos para cambiar contraseña
    old_password: str = Field(..., min_length=6, max_length=50)
    new_password: str = Field(..., min_length=6, max_length=50)