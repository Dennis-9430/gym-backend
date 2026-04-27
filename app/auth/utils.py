# Utilidades para autenticación: JWT y hashing de contraseñas
# Relacionado con: auth/service.py, config.py
"""Authentication utilities: JWT and password hashing"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from app.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Compara contraseña plana con hash guardado
    """Verify a password against a hash"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    # Hashea una contraseña usando bcrypt
    """Hash a password"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    # Crea token JWT con expiración
    # Relacionado con: auth/service.py (create_token), config.py
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    # Decodifica y valida token JWT
    # Relacionado con: auth/router.py (get_current_user), config.py
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def create_initial_users():
    # USUARIOS SEED DESHABILITADOS POR SEGURIDAD
    # Solo crear usuarios demo si ENABLE_DEMO_SEED=true
    # Relacionado con: auth/service.py (initialize_default_users)
    """Create initial users only if demo seed is enabled"""
    import os
    enable_seed = os.getenv("ENABLE_DEMO_SEED", "false").lower() == "true"
    
    if not enable_seed:
        return {}
    
    return {
        "admin": {
            "password_hash": get_password_hash("admin123"),
            "role": "ADMIN",
            "employeeId": None
        },
        "recepcion": {
            "password_hash": get_password_hash("recep123"),
            "role": "RECEPCIONISTA",
            "employeeId": None
        },
        "entrenador": {
            "password_hash": get_password_hash("trainer123"),
            "role": "ENTRENADOR",
            "employeeId": None
        }
    }