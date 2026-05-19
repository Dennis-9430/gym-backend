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
    
    # CORS - Orígenes permitidos (coma separados)
    # En producción: https://app.gymtuempresa.com,https://gymtuempresa.com
    # En local: * (por defecto)
    ALLOWED_ORIGINS: str = "*"
    
    # Demo - Habilitar datos de ejemplo
    ENABLE_DEMO_SEED: bool = False
    
    # Bootstrap - Control de inicialización en startup
    # En producción, desactivar todos los que no sean estrictamente necesarios
    ENABLE_DEFAULT_USERS: bool = True   # Crea admin/receptor si no existen
    ENABLE_SCHEDULER: bool = True       # Inicia scheduler de notificaciones

    # Resend — Email transaccional (reset password, facturas)
    # Obtener API key en https://resend.com/api-keys
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "Gym Management <noreply@gymmanagement.com>"
    FRONTEND_URL: str = "http://localhost:5173"


# ═══════════════════════════════════════════════════════════════════════════════
# PENDIENTES PARA PRODUCCIÓN REAL
# ═══════════════════════════════════════════════════════════════════════════════
#
# Estos puntos están identificados pero NO resueltos — requieren decisión
# de infraestructura o servicios externos antes del deploy.
#
# 1. MIGRACIONES DE ÍNDICES
#    - Extraer create_indexes() de database.py a script independiente.
#    - No dropear/recrear índices en producción al startup.
#    - Probar migración en staging antes de deploy.
#    - Ver app/database.py → create_indexes() docstring.
#
# 2. CORS DEFINITIVO
#    - Definir ALLOWED_ORIGINS con dominios reales.
#    - Ej: ALLOWED_ORIGINS=https://app.migimnasio.com,https://migimnasio.com
#
# 3. URLS PÚBLICAS
#    - Frontend: VITE_API_URL apuntando al backend real.
#    - Backend: dominio público con HTTPS.
#
# 4. MONGODB ATLAS
#    - Cambiar MONGODB_URL a mongodb+srv://...
#    - Usuarios DB con permisos mínimos.
#    - IP allowlist.
#    - Backups automáticos.
#    - TLS obligatorio.
#    - Variables secretas fuera del repo (.env).
#
# 5. EMAIL REAL (facturas, reset password)
#    - Proveedor: SendGrid, Resend, Mailgun o Amazon SES.
#    - No exponer tokens de reset al frontend.
#    - El envío de facturas por email está simulado.
#
# 6. PAGOS Y SUSCRIPCIONES REALES
#    - Proveedor de pagos (Stripe, etc.).
#    - Webhook backend para cambios de estado.
#    - Renovación automática/manual.
#    - Bloqueo por plan.
#
# 7. LOGIN CON SUBDOMINIOS
#    - Cuando el sistema se despliegue con subdominios por tenant,
#      el tenantId se puede extraer del subdominio en lugar del input manual.
#
# 8. JWT SECRET
#    - JWT_SECRET_KEY debe ser una variable de entorno con valor seguro.
#    - El default 'dev-only-jwt-secret-change-in-production' solo para dev.
# ═══════════════════════════════════════════════════════════════════════════════


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