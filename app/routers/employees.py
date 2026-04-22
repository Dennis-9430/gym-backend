# Endpoints para gestión de empleados
# Relacionado con: models/employee.py, auth/router.py, database.py
"""Employees router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List
from bson import ObjectId
from app.models.employee import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse, 
    EmployeeListResponse, EmployeeRole, Permission
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse, UserRole
from app.database import get_database, Collections


router = APIRouter(prefix="/api/employees", tags=["Employees"])


def serialize_employee(doc: dict) -> dict:
    # Converte documento MongoDB a respuesta JSON
    # Relacionado con: models/employee.py
    """Convert MongoDB document to response"""
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.get("", response_model=EmployeeListResponse)
async def list_employees(
    # Lista empleados con paginación y filtros
    # Relacionado con: models/employee.py (EmployeeListResponse), frontend
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[EmployeeRole] = None,
    status: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """List all employees with optional filters"""
    db = get_database()
    
    query = {}
    if role:
        query["role"] = role.value
    if status:
        query["status"] = status
    
    total = await db[Collections.EMPLOYEES].count_documents(query)
    cursor = db[Collections.EMPLOYEES].find(query).skip(skip).limit(limit)
    employees = await cursor.to_list(length=limit)
    
    return {
        "employees": [serialize_employee(e) for e in employees],
        "total": total
    }


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """Get employee by ID"""
    db = get_database()
    
    if not ObjectId.is_valid(employee_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid employee ID"
        )
    
    employee = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found"
        )
    
    return serialize_employee(employee)


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    employee_data: EmployeeCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    """Create new employee (Admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create employees"
        )
    
    db = get_database()
    
    existing = await db[Collections.EMPLOYEES].find_one({
        "$or": [
            {"username": employee_data.username},
            {"documentNumber": employee_data.documentNumber}
        ]
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee with this username or document number already exists"
        )
    
    employee_doc = employee_data.model_dump()
    employee_doc["permissions"] = []
    employee_doc["createdAt"] = employee_doc.get("updatedAt") = None
    
    result = await db[Collections.EMPLOYEES].insert_one(employee_doc)
    employee_doc["_id"] = result.inserted_id
    
    return serialize_employee(employee_doc)


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: str,
    employee_data: EmployeeUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    """Update employee"""
    db = get_database()
    
    if not ObjectId.is_valid(employee_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid employee ID"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found"
        )
    
    update_data = {k: v for k, v in employee_data.model_dump().items() if v is not None}
    if update_data:
        update_data["updatedAt"] = None
    
    await db[Collections.EMPLOYEES].update_one(
        {"_id": ObjectId(employee_id)},
        {"$set": update_data}
    )
    
    updated = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    return serialize_employee(updated)


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """Delete employee (Admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete employees"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(employee_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid employee ID"
        )
    
    result = await db[Collections.EMPLOYEES].delete_one({"_id": ObjectId(employee_id)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found"
        )
    
    return {"message": "Employee deleted successfully"}


@router.put("/{employee_id}/permissions", response_model=EmployeeResponse)
async def update_permissions(
    employee_id: str,
    permissions: List[Permission],
    current_user: UserResponse = Depends(get_current_user)
):
    """Update employee permissions (Admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update permissions"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(employee_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid employee ID"
        )
    
    existing = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found"
        )
    
    await db[Collections.EMPLOYEES].update_one(
        {"_id": ObjectId(employee_id)},
        {"$set": {"permissions": [p.model_dump() for p in permissions], "updatedAt": None}}
    )
    
    updated = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(employee_id)})
    return serialize_employee(updated)