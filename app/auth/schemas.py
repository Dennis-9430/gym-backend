"""Pydantic schemas for authentication"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    """User roles in the system"""
    ADMIN = "ADMIN"
    RECEPCIONISTA = "RECEPCIONISTA"
    ENTRENADOR = "ENTRENADOR"


class TokenData(BaseModel):
    """Token payload data"""
    username: Optional[str] = None
    role: Optional[UserRole] = None


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    """Login request payload"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """User response without sensitive data"""
    username: str
    role: UserRole
    employeeId: Optional[str] = None


class UserCreate(BaseModel):
    """User creation request"""
    username: str
    password: str
    role: UserRole
    employeeId: Optional[str] = None


class PasswordChange(BaseModel):
    """Password change request"""
    old_password: str
    new_password: str = Field(..., min_length=6)