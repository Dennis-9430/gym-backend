# Endpoints para gestión de empleados
# Relacionado con: models/employee.py, database.py, auth/schemas.py
# SEGURIDAD: Todos los endpoints requieren autenticación y filtran por tenantId
"""Employees router"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from typing import Optional
from bson import ObjectId
from jose import JWTError, jwt
from app.models.employee import (
    EmployeeCreate, EmployeeUpdate,
    EmployeeResponse, EmployeeListResponse,
    EmployeeRole, EmployeeStatus
)
from pydantic import BaseModel
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.auth.utils import get_password_hash
from app.database import get_database, Collections
from app.config import settings


router = APIRouter(prefix="/api/employees", tags=["Employees"])


class TenantInfo(BaseModel):
    tenantId: str
    name: str = ""
    plan: str = "BASIC"
    status: str = "ACTIVE"


async def get_tenant_from_header_employees(authorization: str = Header(None)) -> TenantInfo:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )
    
    token = authorization.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id = payload.get("tenantId")
        plan = payload.get("plan", "BASIC")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido"
            )
        
        return TenantInfo(
            tenantId=tenant_id,
            plan=plan
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )


def serialize_employee(doc: dict) -> dict:
    if doc:
        # Convertir _id a string y exponer como 'id' (eliminar _id)
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
        
        # Asegurar que isOwner exista en la respuesta
        if "isOwner" not in doc:
            doc["isOwner"] = False
        
        status = doc.get("status", "ACTIVE")
        if status == "ACTIVO":
            doc["status"] = "ACTIVE"
        elif status == "INACTIVO":
            doc["status"] = "INACTIVE"
        
        role = doc.get("role", "")
        if role == "ENTRENADOR":
            doc["role"] = "RECEPCIONISTA"
        
        if "createdAt" not in doc or doc.get("createdAt") is None:
            doc["createdAt"] = datetime.utcnow()
        if "updatedAt" not in doc or doc.get("updatedAt") is None:
            doc["updatedAt"] = datetime.utcnow()
        
        # Remover password por seguridad
        doc.pop("password", None)
    return doc


@router.get("", response_model=EmployeeListResponse)
async def get_employees(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, description="Buscar por nombre o username"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantInfo = Depends(get_tenant_from_header_employees)
):
    db = get_database()
    query = {"tenantId": tenant.tenantId}
    
    if status_filter:
        query["status"] = status_filter
    
    total = await db[Collections.EMPLOYEES].count_documents(query)
    
    cursor = db[Collections.EMPLOYEES].find(query).skip(skip).limit(limit)
    employees = await cursor.to_list(length=limit)
    
    if search:
        search_lower = search.lower()
        employees = [
            e for e in employees
            if search_lower in e.get("username", "").lower()
            or search_lower in e.get("firstName", "").lower()
            or search_lower in e.get("lastName", "").lower()
        ]
        total = len(employees)
    
    return EmployeeListResponse(
        employees=[EmployeeResponse(**serialize_employee(e)) for e in employees],
        total=total,
    )


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantInfo = Depends(get_tenant_from_header_employees)
):
    db = get_database()
    
    # Validar formato de ObjectId
    if not ObjectId.is_valid(employee_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de empleado inválido"
        )
    
    employee = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id), "tenantId": tenant.tenantId})
    
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empleado no encontrado"
        )
    
    return EmployeeResponse(**serialize_employee(employee))


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    employee_data: EmployeeCreate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantInfo = Depends(get_tenant_from_header_employees)
):
    db = get_database()
    user_role = current_user.role.value
    
    # OWNER (GERENTE) y ADMIN pueden crear empleados
    if user_role not in ["ADMIN", "GERENTE"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores o gerentes pueden crear empleados"
        )
    
    # PROTECCIÓN: ADMIN no puede crear otro ADMIN (pero sí recepcionistas)
    if user_role == "ADMIN" and employee_data.role.value == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un administrador no puede crear otro administrador"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({
        "username": employee_data.username,
        "tenantId": tenant.tenantId
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El username ya existe"
        )
    
    employee_doc = employee_data.model_dump()
    employee_doc["tenantId"] = tenant.tenantId
    employee_doc["createdAt"] = datetime.utcnow()
    employee_doc["updatedAt"] = datetime.utcnow()
    
    # employees NO guarda password — solo perfil
    employee_doc.pop("password", None)
    
    result = await db[Collections.EMPLOYEES].insert_one(employee_doc)
    employee_doc["_id"] = result.inserted_id
    
    # CREAR USUARIO PARA LOGIN en users (fuente única de credenciales)
    if employee_data.password:
        password_hash = get_password_hash(employee_data.password)
        employee_id_str = str(result.inserted_id)
        await db[Collections.USERS].insert_one({
            "username": employee_data.username.lower(),
            "password_hash": password_hash,
            "role": employee_data.role.value,
            "employeeId": employee_id_str,
            "tenantId": tenant.tenantId,
            "createdAt": datetime.utcnow()
        })
    
    # Email de bienvenida en background (solo si tiene credenciales)
    if employee_data.email and employee_data.password:
        import asyncio
        from app.services.email import send_welcome_employee_email
        full_name = f"{employee_data.firstName} {employee_data.lastName}".strip()
        asyncio.create_task(
            send_welcome_employee_email(
                to=employee_data.email,
                name=full_name or employee_data.username,
                username=employee_data.username,
                password=employee_data.password,
                business_name=tenant.name or "Gimnasio",
            )
        )
    
    return EmployeeResponse(**serialize_employee(employee_doc))


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: str,
    update_data: EmployeeUpdate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantInfo = Depends(get_tenant_from_header_employees)
):
    db = get_database()
    user_role = current_user.role.value
    
    # Validar formato de ObjectId
    if not ObjectId.is_valid(employee_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de empleado inválido"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id), "tenantId": tenant.tenantId})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empleado no encontrado"
        )
    
    # PROTECCIÓN: RECEPCIONISTA no puede editar empleados
    if user_role == "RECEPCIONISTA":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los recepcionistas no pueden editar empleados"
        )
    
    # PROTECCIÓN: El OWNER no puede cambiarse a sí mismo - email, role, status
    if existing.get("isOwner", False):
        # El owner solo puede cambiar: firstName, lastName, phone, permissions
        protected_fields = ["email", "role", "status", "isOwner"]
        for field in protected_fields:
            if field in update_data.model_dump() and update_data.model_dump()[field] is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No puedes modificar el campo {field} del owner"
                )
    
    # PROTECCIÓN: ADMIN no puede cambiar role o status de otro ADMIN
    target_role = existing.get("role", "")
    if user_role == "ADMIN" and target_role == "ADMIN":
        update_dict_protected = update_data.model_dump(exclude_unset=True)
        if "role" in update_dict_protected or "status" in update_dict_protected:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Un administrador no puede cambiar el rol o estado de otro administrador"
            )
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updatedAt"] = datetime.utcnow()
    
    # Extraer password para users, NUNCA guardarlo en employees
    password_hash = None
    if "password" in update_dict and update_dict["password"]:
        password_hash = get_password_hash(update_dict["password"])
    update_dict.pop("password", None)
    
    # Validar username único si se está cambiando
    if "username" in update_dict and update_dict["username"]:
        existing_username = await db[Collections.EMPLOYEES].find_one({
            "username": update_dict["username"],
            "tenantId": tenant.tenantId,
            "_id": {"$ne": ObjectId(employee_id)}
        })
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El username ya existe en este negocio"
            )
    
    # SEGURIDAD: filtrar por tenantId al actualizar
    await db[Collections.EMPLOYEES].update_one(
        {"_id": ObjectId(employee_id), "tenantId": tenant.tenantId},
        {"$set": update_dict}
    )
    
    # Si se actualizó la contraseña, actualizar SOLO en users
    if password_hash:
        await db[Collections.USERS].update_one(
            {"employeeId": employee_id, "tenantId": tenant.tenantId},
            {"$set": {"password_hash": password_hash}}
        )
    
    # SEGURIDAD: read-back también filtra por tenantId
    updated = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id), "tenantId": tenant.tenantId})
    return EmployeeResponse(**serialize_employee(updated))


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantInfo = Depends(get_tenant_from_header_employees)
):
    db = get_database()
    user_role = current_user.role.value
    
    # OWNER (GERENTE) y ADMIN pueden eliminar empleados
    if user_role not in ["ADMIN", "GERENTE"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores o gerentes pueden eliminar empleados"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id), "tenantId": tenant.tenantId})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empleado no encontrado"
        )
    
    # PROTECCIÓN: El OWNER no puede eliminarse a sí mismo
    if existing.get("isOwner", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes eliminar al owner principal"
        )
    
    # PROTECCIÓN: ADMIN no puede eliminar a otro ADMIN (pero sí a recepcionistas)
    target_role = existing.get("role", "")
    if user_role == "ADMIN" and target_role == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un administrador no puede eliminar a otro administrador"
        )
    
    # SEGURIDAD: filtrar por tenantId al eliminar
    result = await db[Collections.EMPLOYEES].delete_one({"_id": ObjectId(employee_id), "tenantId": tenant.tenantId})
    
    # También eliminar el usuario asociado para que no pueda hacer login
    await db[Collections.USERS].delete_one({
        "employeeId": employee_id,
        "tenantId": tenant.tenantId
    })
    
    return None


async def initialize_seed_employees():
    # SEGURIDAD: Solo crear si NO existe - evita duplicados
    import os
    enable_seed = os.getenv("ENABLE_DEMO_SEED", "false").lower() == "true"
    
    if not enable_seed:
        return
    
    db = get_database()
    
    # Demo BASIC employees
    basic_employees = [
        {
            "tenantId": "demo-basic-001",
            "username": "admin",
            "documentType": "CEDULA",
            "documentNumber": "12345678",
            "firstName": "Admin",
            "lastName": "Basic",
            "email": "demo-basic@gmail.com",
            "phone": "099123456",
            "role": "GERENTE",  # El owner siempre es GERENTE
            "status": "ACTIVE",
            "isOwner": True,  # Owner del demo basic
            "password": "demoBasic123",  # Contraseña hasheada se genera después
        },
        {
            "tenantId": "demo-basic-001",
            "username": "recepcion",
            "documentType": "CEDULA",
            "documentNumber": "87654321",
            "firstName": "Maria",
            "lastName": "Gonzalez",
            "email": "maria@demo-basic.com",
            "phone": "099987654",
            "role": "RECEPCIONISTA",
            "status": "ACTIVE",
            "isOwner": False,
        },
    ]
    
    # Solo crear si NO existe (buscar por tenantId + username)
    for emp in basic_employees:
        existing = await db[Collections.EMPLOYEES].find_one({
            "tenantId": emp["tenantId"],
            "username": emp["username"]
        })
        if not existing:
            # Guardar password antes de limpiar el doc
            raw_password = emp.pop("password", None)
            emp["createdAt"] = datetime.utcnow()
            emp["updatedAt"] = datetime.utcnow()
            result = await db[Collections.EMPLOYEES].insert_one(emp)
            
            # Crear user en users para que pueda hacer login
            if raw_password:
                await db[Collections.USERS].insert_one({
                    "username": emp["username"].lower(),
                    "password_hash": get_password_hash(raw_password),
                    "role": emp.get("role", "RECEPCIONISTA"),
                    "employeeId": str(result.inserted_id),
                    "tenantId": emp["tenantId"],
                    "createdAt": datetime.utcnow()
                })
    
    # Demo PRO employees
    pro_employees = [
        {
            "tenantId": "demo-pro-001",
            "username": "admin",
            "documentType": "CEDULA",
            "documentNumber": "12345678",
            "firstName": "Admin",
            "lastName": "Pro",
            "email": "demo-pro@gmail.com",
            "phone": "099123456",
            "role": "GERENTE",  # El owner siempre es GERENTE
            "status": "ACTIVE",
            "isOwner": True,  # Owner del demo pro
            "password": "demoPro123",
        },
    ]
    
    for emp in pro_employees:
        existing = await db[Collections.EMPLOYEES].find_one({
            "tenantId": emp["tenantId"],
            "username": emp["username"]
        })
        if not existing:
            # Guardar password antes de limpiar el doc
            raw_password = emp.pop("password", None)
            emp["createdAt"] = datetime.utcnow()
            emp["updatedAt"] = datetime.utcnow()
            result = await db[Collections.EMPLOYEES].insert_one(emp)
            
            # Crear user en users para que pueda hacer login
            if raw_password:
                await db[Collections.USERS].insert_one({
                    "username": emp["username"].lower(),
                    "password_hash": get_password_hash(raw_password),
                    "role": emp.get("role", "RECEPCIONISTA"),
                    "employeeId": str(result.inserted_id),
                    "tenantId": emp["tenantId"],
                    "createdAt": datetime.utcnow()
                })
