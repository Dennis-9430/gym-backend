# Lógica de negocio para autenticación
# Relacionado con: auth/router.py, auth/utils.py, auth/schemas.py
"""Authentication service"""
from datetime import timedelta
from typing import Optional
from bson import ObjectId
from app.auth.schemas import UserResponse, LoginRequest, Token, UserRole
from app.auth.utils import verify_password, create_access_token, create_initial_users
from app.database import get_database, Collections
from app.config import settings


# ──────────────────────────────────────────────────────────────────────────────
# DECISIÓN DE LOGIN MULTI-TENANT
# ──────────────────────────────────────────────────────────────────────────────
# El sistema soporta dos modos de login:
#
# 1. GLOBAL (backward compatible): username + password sin tenantId.
#    → Busca usuario por username en toda la colección (índice no único).
#    → Requiere usernames únicos globalmente.
#    → Útil para migración o cuando hay un solo tenant.
#
# 2. MULTI-TENANT (recomendado para SaaS): businessCode + username + password.
#    → businessCode (slug) identifica el gimnasio/tenant.
#    → Se resuelve a tenantId, y la búsqueda de usuario se scopea.
#    → Permite mismo username en diferentes tenants.
#    → El frontend envía businessCode desde el campo "Código del Negocio"
#      o tenantId UUID desde localStorage.
#
# FLUJO ACTUAL:
# - Login global (sin tenantId) → funciona, pero limita el SaaS.
# - Login con businessCode/tenantId → multi-tenant real, recomendado.
# - Después del registro, businessCode se pasa automáticamente al login.
# - Login demo pre-filla demo-basic / demo-premium bloqueado.
#
# PENDIENTE PARA PRODUCCIÓN:
# - Cuando se despliegue con subdominios (tenant.app.com), el tenantId
#   se podrá extraer del subdominio sin input del usuario.
# ──────────────────────────────────────────────────────────────────────────────

async def authenticate_user(username: str, password: str, tenant_id: Optional[str] = None) -> Optional[UserResponse]:
    # Valida credenciales del usuario contra la base de datos
    # Relacionado con: auth/router.py (login), auth/utils.py (verify_password)
    # Nota: tenant_id es opcional para login legacy (sin tenant).
    # Para multi-tenant real, enviar tenant_id scopea la búsqueda.
    """Authenticate user with username and password"""
    db = get_database()
    query = {"username": username.lower()}
    if tenant_id:
        query["tenantId"] = tenant_id
    user_doc = await db[Collections.USERS].find_one(query)
    
    if not user_doc:
        return None
    
    if not verify_password(password, user_doc["password_hash"]):
        return None
    
    # Verificar status del empleado si tiene employeeId
    if user_doc.get("employeeId"):
        try:
            employee = await db[Collections.EMPLOYEES].find_one(
                {"_id": ObjectId(user_doc["employeeId"])}
            )
        except Exception:
            employee = None
        
        if employee:
            status = employee.get("status", "ACTIVE")
            if status == "INACTIVE":
                # Retornar el usuario pero marcado como inactivo
                # El router verificará isInactive y throwará 403
                return UserResponse(
                    username=user_doc["username"],
                    role=UserRole(user_doc["role"]),
                    employeeId=user_doc.get("employeeId"),
                    tenantId=user_doc.get("tenantId"),
                    isOwner=user_doc.get("isOwner", False),
                    plan=user_doc.get("plan", "BASIC"),
                    isInactive=True  # Campo especial para indicar cuenta inactiva
                )
    
    return UserResponse(
        username=user_doc["username"],
        role=UserRole(user_doc["role"]),
        employeeId=user_doc.get("employeeId"),
        tenantId=user_doc.get("tenantId"),
        isOwner=user_doc.get("isOwner", False),
        plan=user_doc.get("plan", "BASIC")
    )


async def create_token(username: str, role: UserRole, tenant_id: str = None, is_owner: bool = False, plan: str = "BASIC", employee_id: str = None) -> Token:
    # Genera token JWT para el usuario
    # Relacionado con: auth/router.py (login), config.py
    """Create JWT token for user"""
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    data = {"sub": username, "role": role.value}
    
    if tenant_id:
        data["tenantId"] = tenant_id
    if is_owner:
        data["isOwner"] = True
    if plan:
        data["plan"] = plan
    if employee_id:
        data["employeeId"] = employee_id
    
    access_token = create_access_token(
        data=data,
        expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


async def get_user_by_username(username: str, tenant_id: Optional[str] = None) -> Optional[dict]:
    # Busca usuario por nombre de usuario, opcionalmente scoped por tenantId
    # Relacionado con: auth/router.py (register, change_password)
    """Get user by username, optionally scoped to tenant"""
    db = get_database()
    query = {"username": username.lower()}
    if tenant_id:
        query["tenantId"] = tenant_id
    return await db[Collections.USERS].find_one(query)


async def create_user(username: str, password_hash: str, role: UserRole, employee_id: Optional[str] = None, tenant_id: Optional[str] = None) -> dict:
    # Crea nuevo usuario en la base de datos
    # Relacionado con: auth/router.py (register)
    """Create new user"""
    db = get_database()
    user_doc = {
        "username": username.lower(),
        "password_hash": password_hash,
        "role": role.value,
        "employeeId": employee_id,
    }
    if tenant_id:
        user_doc["tenantId"] = tenant_id
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