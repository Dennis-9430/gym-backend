# Rutas de autenticación (login, register, logout)
# Relacionado con: auth/service.py, auth/schemas.py, auth/utils.py
"""Authentication router"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional, List
from app.auth.schemas import Token, UserResponse, UserCreate, PasswordChange
from app.auth.service import authenticate_user, create_token, get_user_by_username, initialize_default_users
from app.auth.utils import get_password_hash, decode_token
from app.auth.schemas import UserRole


router = APIRouter(prefix="/api/auth", tags=["Authentication"])
# OAuth2 scheme para obtener token del header
# Relacionado con: auth/service.py (create_token)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserResponse:
    # Extrae y valida el usuario del token JWT
    # Relacionado con: auth/utils.py (decode_token)
    """Get current authenticated user from token"""
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username: str = payload.get("sub")
    role: str = payload.get("role")
    employee_id: Optional[str] = payload.get("employeeId")
    tenant_id: Optional[str] = payload.get("tenantId")
    is_owner: Optional[bool] = payload.get("isOwner", False)
    plan: Optional[str] = payload.get("plan")
    
    if username is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return UserResponse(
        username=username,
        role=UserRole(role),
        employeeId=employee_id,
        tenantId=tenant_id,
        isOwner=is_owner,
        plan=plan
    )


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Valida credenciales y retorna token JWT
    # Relacionado con: auth/service.py (authenticate_user, create_token)
    """Login endpoint"""
    user = await authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verificar si la cuenta está inactiva
    if getattr(user, 'isInactive', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está INACTIVA. Contacta al administrador.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Auto-cleanup para cuentas demo: borra datos previos al login
    if user.tenantId:
        from app.database import get_database, Collections
        db = get_database()
        tenant = await db[Collections.TENANTS].find_one({"tenantId": user.tenantId})
        if tenant and tenant.get("isDemo", False):
            collections_to_clean = [
                Collections.SALES,
                Collections.CLIENTS,
                Collections.INVOICES,
                Collections.PRODUCTS,
                Collections.ATTENDANCE,
            ]
            for collection_name in collections_to_clean:
                # Solo borra datos NO semilla (isSeed != true)
                await db[collection_name].delete_many({
                    "tenantId": user.tenantId,
                    "isSeed": {"$ne": True},
                })
    
    # Incluir toda la información del usuario en el token
    token = await create_token(
        username=user.username,
        role=user.role,
        tenant_id=user.tenantId,
        is_owner=user.isOwner,
        plan=user.plan,
        employee_id=user.employeeId
    )
    return token


@router.post("/logout")
async def logout(current_user: UserResponse = Depends(get_current_user)):
    # Cierra sesión (el token se invalida en el frontend)
    # Relacionado con: get_current_user
    """Logout endpoint"""
    return {"message": "Logged out successfully"}


@router.post("/verify-password")
async def verify_password(
    password_data: dict,
    authorization: str = Header(None)
):
    from app.auth.utils import verify_password as verify_pwd, decode_token
    from app.database import get_database, Collections
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )
    
    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )
    
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin usuario"
        )
    
    db = get_database()
    
    # Buscar en users (fuente única de credenciales) por username
    user_doc = await db[Collections.USERS].find_one({
        "username": username.lower()
    })
    
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    password = password_data.get("password", "")
    stored_hash = user_doc.get("password_hash", "")
    
    if not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario no tiene contraseña configurada"
        )
    
    if not verify_pwd(password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña incorrecta",
        )
    
    return {"valid": True}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    # Retorna información del usuario actual
    # Relacionado con: get_current_user
    """Get current user info"""
    return current_user


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, current_user: UserResponse = Depends(get_current_user)):
    # Crea un nuevo usuario (solo admins)
    # Relacionado con: get_current_user, auth/service.py (create_user)
    """Register new user (admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create users"
        )
    
    existing = await get_user_by_username(user_data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    password_hash = get_password_hash(user_data.password)
    from app.auth.service import create_user
    new_user = await create_user(
        username=user_data.username,
        password_hash=password_hash,
        role=user_data.role,
        employee_id=user_data.employeeId
    )
    
    return UserResponse(
        username=new_user["username"],
        role=UserRole(new_user["role"]),
        employeeId=new_user.get("employeeId")
    )


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: UserResponse = Depends(get_current_user)
):
    # Cambia la contraseña del usuario actual
    # Relacionado con: get_current_user, auth/utils.py (verify_password)
    """Change password"""
    from app.database import get_database, Collections
    
    user_doc = await get_user_by_username(current_user.username)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    from app.auth.utils import verify_password
    if not verify_password(password_data.old_password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    new_hash = get_password_hash(password_data.new_password)
    db = get_database()
    await db[Collections.USERS].update_one(
        {"username": current_user.username},
        {"$set": {"password_hash": new_hash}}
    )
    
    return {"message": "Password changed successfully"}