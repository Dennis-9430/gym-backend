# Utilidades para autenticación: JWT y hashing de contraseñas
# Relacionado con: auth/service.py, config.py
"""Authentication utilities: JWT and password hashing"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings


# Contexto para hashear contraseñas con bcrypt
# Relacionado con: auth/service.py, auth/router.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Compara contraseña plana con hash guardado
    # Relacionado con: auth/service.py (authenticate_user)
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    # Hashea una contraseña usando bcrypt
    # Relacionado con: auth/router.py (register), auth/service.py
    """Hash a password"""
    return pwd_context.hash(password)


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
    # Define usuarios por defecto (admin/admin123, recep/recep123, trainer/trainer123)
    # Relacionado con: auth/service.py (initialize_default_users)
    """Create initial users with hashed passwords"""
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
        },
        "dennis": {
            "password_hash": get_password_hash("123456"),
            "role": "RECEPCIONISTA",
            "employeeId": None
        }
    }