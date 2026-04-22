# Endpoints para gestión de servicios/membresías
# Relacionado con: models/service.py, auth/router.py, database.py
"""Services (Memberships) router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from bson import ObjectId
from app.models.service import (
    ServiceCreate, ServiceUpdate, ServiceResponse, ServiceListResponse
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse, UserRole
from app.database import get_database, Collections


router = APIRouter(prefix="/api/services", tags=["Services"])


def serialize_service(doc: dict) -> dict:
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.get("", response_model=ServiceListResponse)
async def list_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    query = {}
    if active_only:
        query["isActive"] = True
    
    total = await db[Collections.SERVICES].count_documents(query)
    cursor = db[Collections.SERVICES].find(query).skip(skip).limit(limit)
    services = await cursor.to_list(length=limit)
    
    return {
        "services": [serialize_service(s) for s in services],
        "total": total
    }


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    if not ObjectId.is_valid(service_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid service ID"
        )
    
    service = await db[Collections.SERVICES].find_one({"_id": ObjectId(service_id)})
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    
    return serialize_service(service)


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    service_data: ServiceCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create services"
        )
    
    db = get_database()
    
    existing = await db[Collections.SERVICES].find_one({"name": service_data.name})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service with this name already exists"
        )
    
    service_doc = service_data.model_dump()
    service_doc["createdAt"] = None
    service_doc["updatedAt"] = None
    
    result = await db[Collections.SERVICES].insert_one(service_doc)
    service_doc["_id"] = str(result.inserted_id)
    
    return service_doc


@router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: str,
    service_data: ServiceUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update services"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(service_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid service ID"
        )
    
    existing = await db[Collections.SERVICES].find_one({"_id": ObjectId(service_id)})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    
    update_data = {k: v for k, v in service_data.model_dump().items() if v is not None}
    
    if update_data:
        await db[Collections.SERVICES].update_one(
            {"_id": ObjectId(service_id)},
            {"$set": update_data}
        )
    
    updated = await db[Collections.SERVICES].find_one({"_id": ObjectId(service_id)})
    return serialize_service(updated)


@router.delete("/{service_id}")
async def delete_service(
    service_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete services"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(service_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid service ID"
        )
    
    result = await db[Collections.SERVICES].delete_one({"_id": ObjectId(service_id)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    
    return {"message": "Service deleted successfully"}
