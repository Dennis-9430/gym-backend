# Esquemas Pydantic para validación de autenticación
# Relacionado con: auth/router.py, auth/service.py
"""Pydantic schemas for authentication"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    # Roles de usuario en el sistema
    # Relacionado con: auth/router.py, auth/service.py
    """User roles in the system"""
    ADMIN = "ADMIN"
    RECEPCIONISTA = "RECEPCIONISTA"
    ENTRENADOR = "ENTRENADOR"


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


class UserCreate(BaseModel):
    # Datos para crear nuevo usuario
    # Relacionado con: auth/router.py (register)
    """User creation request"""
    username: str
    password: str
    role: UserRole
    employeeId: Optional[str] = None


class PasswordChange(BaseModel):
    # Datos para cambiar contraseña
    # Relacionado con: auth/router.py (change_password)
    """Password change request"""
    old_password: str
    new_password: str = Field(..., min_length=6)