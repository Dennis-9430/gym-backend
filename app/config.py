# Configuración del aplicativo usando pydantic-settings
# Relacionado con: .env, database.py, main.py
"""Application configuration using pydantic-settings"""
from pydantic_settings import BaseSettings
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
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 horas — sesión dura todo el día laboral
    
    # Cookie HttpOnly — JWT se envía como cookie segura además del body
    # En producción (DEBUG=False), COOKIE_SECURE se fuerza a True automáticamente
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"  # lax | strict | none — se auto-cambia a "none" en producción (ver __init__)
    COOKIE_DOMAIN: str = ""       # Dominio de la cookie (vacío = solo origen actual)
    
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
    
    # CORS - Orígenes permitidos
    # En producción: https://gym-management-nine-azure.vercel.app
    # En local: http://localhost:5173
    ALLOWED_ORIGINS: list = ["https://gym-management-nine-azure.vercel.app", "http://localhost:5173"]
    
    # Demo - Habilitar datos de ejemplo
    ENABLE_DEMO_SEED: bool = False
    
    # Bootstrap - Control de inicialización en startup
    # En producción, desactivar todos los que no sean estrictamente necesarios
    ENABLE_DEFAULT_USERS: bool = True   # Crea admin/receptor si no existen
    ENABLE_SCHEDULER: bool = True       # Inicia scheduler de notificaciones

    # Brevo (ex Sendinblue) — Email transaccional (reset password, facturas)
    # Obtener API key en https://app.brevo.com/settings/api/key
    BREVO_API_KEY: str = ""
    EMAIL_FROM: str = "pinzonfabricio9430@gmail.com"
    EMAIL_FROM_NAME: str = "Gym Management"
    FRONTEND_URL: str = "http://localhost:5173"

    # SUPER_ADMIN — Configuración para el superadmin del sistema
    SUPER_ADMIN_EMAIL: str = ""
    SUPER_ADMIN_PASSWORD: str = ""
    SUPER_ADMIN_NAME: str = "System Administrator"


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
# ═══════════════════════════════════════════════════════════════════════════════


    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Permite campos extra en .env
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # JWT: en desarrollo generamos una clave por defecto; en producción es obligatoria
        if not self.JWT_SECRET_KEY:
            if self.DEBUG:
                self.JWT_SECRET_KEY = "dev-only-jwt-secret-change-in-production"
            else:
                raise ValueError(
                    "JWT_SECRET_KEY es obligatorio en producción. "
                    "Configúralo en el archivo .env o como variable de entorno."
                )

        # En producción (DEBUG=False), forzamos COOKIE_SECURE=True y COOKIE_SAMESITE="lax"
        # Con el proxy de Vercel, las requests son same-origin → SameSite=Lax funciona.
        if not self.DEBUG:
            if not self.COOKIE_SECURE:
                self.COOKIE_SECURE = True
            if self.COOKIE_SAMESITE != "lax":
                self.COOKIE_SAMESITE = "lax"


settings = Settings()