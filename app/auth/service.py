# Lógica de negocio para autenticación
# Relacionado con: auth/router.py, auth/utils.py, auth/schemas.py
"""Authentication service"""
from datetime import timedelta
from typing import Optional
from app.auth.schemas import UserResponse, LoginRequest, Token, UserRole
from app.auth.utils import verify_password, create_access_token, create_initial_users
from app.database import get_database, Collections
from app.config import settings


async def authenticate_user(username: str, password: str) -> Optional[UserResponse]:
    # Valida credenciales del usuario contra la base de datos
    # Relacionado con: auth/router.py (login), auth/utils.py (verify_password)
    """Authenticate user with username and password"""
    db = get_database()
    user_doc = await db[Collections.USERS].find_one({"username": username.lower()})
    
    if not user_doc:
        return None
    
    if not verify_password(password, user_doc["password_hash"]):
        return None
    
    return UserResponse(
        username=user_doc["username"],
        role=UserRole(user_doc["role"]),
        employeeId=user_doc.get("employeeId")
    )


async def create_token(username: str, role: UserRole) -> Token:
    # Genera token JWT para el usuario
    # Relacionado con: auth/router.py (login), config.py
    """Create JWT token for user"""
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username, "role": role.value},
        expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


async def get_user_by_username(username: str) -> Optional[dict]:
    # Busca usuario por nombre de usuario
    # Relacionado con: auth/router.py (register, change_password)
    """Get user by username"""
    db = get_database()
    return await db[Collections.USERS].find_one({"username": username.lower()})


async def create_user(username: str, password_hash: str, role: UserRole, employee_id: Optional[str] = None) -> dict:
    # Crea nuevo usuario en la base de datos
    # Relacionado con: auth/router.py (register)
    """Create new user"""
    db = get_database()
    user_doc = {
        "username": username.lower(),
        "password_hash": password_hash,
        "role": role.value,
        "employeeId": employee_id
    }
    result = await db[Collections.USERS].insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return user_doc


async def initialize_default_users():
    # Crea usuarios por defecto al iniciar la app (admin/admin, receptor/receptor)
    # Relacionado con: main.py (lifespan), auth/utils.py
    """Initialize default users if they don't exist"""
    db = get_database()
    initial_users = create_initial_users()
    
    for username, data in initial_users.items():
        existing = await db[Collections.USERS].find_one({"username": username})
        if not existing:
            await db[Collections.USERS].insert_one({
                "username": username,
                "password_hash": data["password_hash"],
                "role": data["role"],
                "employeeId": data["employeeId"]
            })
            print(f"Created default user: {username}")