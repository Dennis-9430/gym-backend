# Configuración del aplicativo usando pydantic-settings
# Relacionado con: .env, database.py, main.py
"""Application configuration using pydantic-settings"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Carga configuración desde variables de entorno
    # Relacionado con: .env
    """Application settings loaded from environment variables"""
    
    # MongoDB - Configuración de base de datos
    # Relacionado con: database.py
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "gym_db"
    
    # JWT - Configuración de autenticación
    # IMPORTANTE: Cambiar en producción con secrets.generate() o heredar de environment
    # Relacionado con: auth/utils.py
    JWT_SECRET_KEY: str = "gym-jwt-secret-2024"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # API - Configuración del servidor
    # Relacionado con: main.py
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()