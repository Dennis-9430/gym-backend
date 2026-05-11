# Endpoints para gestión de servicios/membresías
# Relacionado con: models/service.py, auth/router.py, database.py
"""Services (Memberships) router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from datetime import datetime
from bson import ObjectId
from app.models.service import (
    ServiceCreate, ServiceUpdate, ServiceResponse, ServiceListResponse
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse, UserRole
from app.database import get_database, Collections
from app.utils.demo_protect import check_seed_protected


router = APIRouter(prefix="/api/services", tags=["Services"])


def serialize_service(doc: dict) -> dict:
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
    return doc


@router.get("", response_model=ServiceListResponse)
async def list_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    min_price: Optional[float] = Query(None, description="Precio mínimo para filtrar"),
    max_price: Optional[float] = Query(None, description="Precio máximo para filtrar"),
    service_type: Optional[str] = Query(None, description="Tipo de servicio: daily, membership, special"),
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    # Filtrar por tenant del usuario actual
    query = {"tenantId": current_user.tenantId}
    if active_only:
        query["isActive"] = True
    
    # Filtro por rango de precio
    if min_price is not None or max_price is not None:
        price_filter = {}
        if min_price is not None:
            price_filter["$gte"] = min_price
        if max_price is not None:
            price_filter["$lte"] = max_price
        query["price"] = price_filter
    
    # Filtro por tipo de servicio
    if service_type:
        query["type"] = service_type
    
    total = await db[Collections.SERVICES].count_documents(query)
    cursor = db[Collections.SERVICES].find(query).sort([("price", 1)]).skip(skip).limit(limit)
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
    
    service = await db[Collections.SERVICES].find_one({
        "_id": ObjectId(service_id),
        "tenantId": current_user.tenantId
    })
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
    if current_user.role not in [UserRole.ADMIN, UserRole.GERENTE]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores o gerentes pueden crear servicios"
        )
    
    db = get_database()
    
    # Verificar nombre único por tenant
    existing = await db[Collections.SERVICES].find_one({
        "name": service_data.name,
        "tenantId": current_user.tenantId
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un servicio con este nombre"
        )
    
    service_doc = service_data.model_dump()
    service_doc["tenantId"] = current_user.tenantId  # Asignar tenant del usuario
    service_doc["createdAt"] = datetime.utcnow()
    service_doc["updatedAt"] = datetime.utcnow()
    
    result = await db[Collections.SERVICES].insert_one(service_doc)
    service_doc["_id"] = str(result.inserted_id)
    
    return serialize_service(service_doc)


@router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: str,
    service_data: ServiceUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.GERENTE]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores o gerentes pueden actualizar servicios"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(service_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid service ID"
        )
    
    existing = await db[Collections.SERVICES].find_one({
        "_id": ObjectId(service_id),
        "tenantId": current_user.tenantId
    })
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    
    # Proteger seed data en cuentas demo
    if current_user.tenantId:
        await check_seed_protected(db, current_user.tenantId, Collections.SERVICES, service_id, "modificados")
    
    update_data = {k: v for k, v in service_data.model_dump().items() if v is not None}
    update_data["updatedAt"] = datetime.utcnow()
    
    if update_data:
        await db[Collections.SERVICES].update_one(
            {"_id": ObjectId(service_id), "tenantId": current_user.tenantId},
            {"$set": update_data}
        )
    
    updated = await db[Collections.SERVICES].find_one({
        "_id": ObjectId(service_id),
        "tenantId": current_user.tenantId
    })
    return serialize_service(updated)


@router.delete("/{service_id}")
async def delete_service(
    service_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.GERENTE]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores o gerentes pueden eliminar servicios"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(service_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid service ID"
        )
    
    # Proteger seed data en cuentas demo
    if current_user.tenantId:
        await check_seed_protected(db, current_user.tenantId, Collections.SERVICES, service_id, "eliminados")
    
    # Hard delete - eliminar de la base de datos
    result = await db[Collections.SERVICES].delete_one({
        "_id": ObjectId(service_id),
        "tenantId": current_user.tenantId
    })
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    
    return {"message": "Servicio eliminado correctamente"}
