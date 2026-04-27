# Configuración del aplicativo usando pydantic-settings
# Relacionado con: .env, database.py, main.py
"""Application configuration using pydantic-settings"""
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional
import os


class Settings(BaseSettings):
    # Carga configuración desde variables de entorno
    # Relacionado con: .env
    """Application settings loaded from environment variables"""
    
    # MongoDB - Configuración de base de datos
    # Relacionado con: database.py
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "gym_db"
    
    # JWT - Configuración de autenticación
    # IMPORTANTE: En producción debe venir de variable de entorno
    # Relacionado con: auth/utils.py
    JWT_SECRET_KEY: str = Field(default="", description="JWT secret key - obligatorio en producción")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    @field_validator("JWT_SECRET_KEY", mode="before")
    @classmethod
    def validate_jwt_secret(cls, v):
        if not v or v == "":
            raise ValueError("JWT_SECRET_KEY es obligatorio en producción. Configuralo en variable de entorno.")
        return v
    
    # API - Configuración del servidor
    # Relacionado con: main.py
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    
    # Twilio - Configuración de WhatsApp
    # Obtener de https://console.twilio.com
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = "+14155238886"  # Default Twilio sandbox
    
    # Demo - Habilitar datos de ejemplo
    ENABLE_DEMO_SEED: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Permite campos extra en .env
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Validación de JWT en producción
        if not self.JWT_SECRET_KEY:
            # En desarrollo permite默认值 temporal, en producción debefallar
            if os.getenv("DEBUG", "").lower() == "true":
                self.JWT_SECRET_KEY = "dev-only-jwt-secret-change-in-production"
            else:
                raise ValueError("JWT_SECRET_KEY es obligatorio en producción. Define la variable de entorno.")


settings = Settings()