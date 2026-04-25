# Endpoints para gestión de empleados
# Relacionado con: models/employee.py, database.py, auth/schemas.py
"""Employees router"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from bson import ObjectId
from app.models.employee import (
    EmployeeCreate, EmployeeUpdate,
    EmployeeResponse, EmployeeListResponse,
    EmployeeRole, EmployeeStatus
)
from app.models.tenant import TenantResponse
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections


router = APIRouter(prefix="/api/employees", tags=["Employees"])


def serialize_employee(doc: dict) -> dict:
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        
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
        
        doc.pop("_id", None)
    return doc


@router.get("", response_model=EmployeeListResponse)
async def get_employees(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, description="Buscar por nombre o username"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: UserResponse = Depends(get_current_user),
):
    db = get_database()
    query = {}
    
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
):
    db = get_database()
    employee = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    
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
):
    db = get_database()
    if current_user.role.value not in ["ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores pueden crear empleados"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({
        "username": employee_data.username
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El username ya existe"
        )
    
    employee_doc = employee_data.model_dump()
    employee_doc.pop("password", None)
    employee_doc["createdAt"] = datetime.utcnow()
    employee_doc["updatedAt"] = datetime.utcnow()
    
    result = await db[Collections.EMPLOYEES].insert_one(employee_doc)
    employee_doc["_id"] = result.inserted_id
    
    return EmployeeResponse(**serialize_employee(employee_doc))


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: str,
    update_data: EmployeeUpdate,
    current_user: UserResponse = Depends(get_current_user),
):
    db = get_database()
    if current_user.role.value not in ["ADMIN", "RECEPCIONISTA"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para actualizar empleados"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empleado no encontrado"
        )
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updatedAt"] = datetime.utcnow()
    
    await db[Collections.EMPLOYEES].update_one(
        {"_id": ObjectId(employee_id)},
        {"$set": update_dict}
    )
    
    updated = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    return EmployeeResponse(**serialize_employee(updated))


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    db = get_database()
    if current_user.role.value != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores pueden eliminar empleados"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empleado no encontrado"
        )
    
    result = await db[Collections.EMPLOYEES].delete_one({"_id": ObjectId(employee_id)})
    
    return None


async def initialize_seed_employees():
    from datetime import datetime
    from app.auth.utils import get_password_hash
    
    db = get_database()
    
    existing = await db[Collections.EMPLOYEES].count_documents({})
    if existing > 0:
        return
    
    seed_employees = [
        {
            "username": "admin",
            "documentType": "CEDULA",
            "documentNumber": "12345678",
            "firstName": "Admin",
            "lastName": "Principal",
            "email": "admin@gym.com",
            "phone": "099123456",
            "role": "ADMIN",
            "status": "ACTIVE",
            "tenantId": "demo-gym",
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        },
        {
            "username": "recepcion",
            "documentType": "CEDULA",
            "documentNumber": "87654321",
            "firstName": "Maria",
            "lastName": "Gonzalez",
            "email": "maria@gym.com",
            "phone": "099987654",
            "role": "RECEPCIONISTA",
            "status": "ACTIVE",
            "tenantId": "demo-gym",
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        },
    ]
    
    for emp in seed_employees:
        await db[Collections.EMPLOYEES].insert_one(emp)
    
    print(f"Initialized {len(seed_employees)} seed employees")