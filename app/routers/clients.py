# Endpoints para gestión de clientes
# Relacionado con: models/client.py, auth/router.py, database.py
"""Clients router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from typing import Optional
from bson import ObjectId
from jose import JWTError, jwt
from app.models.client import (
    ClientCreate, ClientUpdate, ClientResponse, 
    ClientListResponse, MembershipStatus
)
from app.models.tenant import TenantResponse, SubscriptionPlan, SubscriptionStatus
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections
from app.utils.sanitize import sanitize_search_input
from app.config import settings


router = APIRouter(prefix="/api/clients", tags=["Clients"])


def serialize_client(doc: dict) -> dict:
    # Convierte ObjectId a string para JSON
    # Relacionado con: models/client.py
    if doc:
        from bson import ObjectId
        oid = doc.get("_id")
        if oid:
            doc["id"] = str(oid)
            doc.pop("_id", None)
        else:
            doc["id"] = doc.get("id", 0)
    return doc


async def get_tenant_from_header(authorization: str = Header(None)) -> TenantResponse:
    # Extrae el tenant del token JWT (acepta token de tenant)
    print(f"DEBUG: auth header = {authorization}")
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato inválido"
        )
    
    token = authorization.replace("Bearer ", "")
    print(f"DEBUG: token = {token[:50]}...")
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        print(f"DEBUG: payload = {payload}")
        tenant_id = payload.get("tenantId")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token sin tenantId"
            )
        
        # Retornar solo con los datos necesarios del tenant
        return TenantResponse(
            _id=tenant_id,
            tenantId=tenant_id,
            email=payload.get("sub", ""),
            businessName=payload.get("businessName", ""),
            businessPhone=payload.get("businessPhone", ""),
            businessAddress=payload.get("businessAddress", ""),
            businessRuc=payload.get("businessRuc", ""),
            plan=SubscriptionPlan.BASIC,
            subscriptionStatus=SubscriptionStatus.ACTIVE
        )
    
    except JWTError as e:
        print(f"DEBUG JWTError: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )


@router.get("", response_model=ClientListResponse)
async def list_clients(
    # Lista clientes con paginación y filtros
    # Relacionado con: models/client.py (ClientListResponse), frontend
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[MembershipStatus] = None,
    search: Optional[str] = None,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    # Usar tenantId del token de tenant
    query = {"tenantId": tenant.tenantId}
    if status:
        query["membershipStatus"] = status.value
    
    # Sanitizar búsqueda - búsqueda exacta
    sanitized = sanitize_search_input(search)
    if sanitized:
        query["$or"] = [
            {"firstName": sanitized},
            {"lastName": sanitized},
            {"documentNumber": sanitized}
        ]
    
    try:
        total = await db[Collections.CLIENTS].count_documents(query)
        cursor = db[Collections.CLIENTS].find(query).skip(skip).limit(limit)
        clients = await cursor.to_list(length=limit)
        
        return {"clients": [serialize_client(c) for c in clients], "total": total}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    # Obtiene un cliente por ID
    # Relacionado con: models/client.py (ClientResponse)
    client_id: int,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    client = await db[Collections.CLIENTS].find_one({"id": client_id, "tenantId": tenant.tenantId})
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    return client


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    # Crea un nuevo cliente
    # Relacionado con: models/client.py (ClientCreate)
    client_data: ClientCreate,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    # Verificar con tenantId
    existing = await db[Collections.CLIENTS].find_one({
        "documentNumber": client_data.documentNumber,
        "tenantId": tenant.tenantId
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client with this document number already exists"
        )
    
    last_client = await db[Collections.CLIENTS].find_one(sort=[("id", -1)])
    next_id = (last_client["id"] + 1) if last_client else 1
    
    client_doc = client_data.model_dump()
    client_doc["id"] = next_id
    client_doc["tenantId"] = tenant.tenantId
    client_doc["createdAt"] = None
    client_doc["membershipStartDate"] = None
    client_doc["membershipEndDate"] = None
    
    result = await db[Collections.CLIENTS].insert_one(client_doc)
    
    return {**client_doc, "_id": next_id}


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    # Actualiza un cliente existente
    # Relacionado con: models/client.py (ClientUpdate)
    client_id: int,
    client_data: ClientUpdate,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    existing = await db[Collections.CLIENTS].find_one({"id": client_id, "tenantId": tenant.tenantId})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    update_data = {k: v for k, v in client_data.model_dump().items() if v is not None}
    
    if update_data:
        await db[Collections.CLIENTS].update_one(
            {"id": client_id, "tenantId": tenant.tenantId},
            {"$set": update_data}
        )
    
    updated = await db[Collections.CLIENTS].find_one({"id": client_id, "tenantId": tenant.tenantId})
    return updated


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    result = await db[Collections.CLIENTS].delete_one({"id": client_id, "tenantId": tenant.tenantId})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    return {"message": "Client deleted successfully"}


@router.put("/{client_id}/membership", response_model=ClientResponse)
async def update_membership(
    client_id: int,
    membership: str,
    membershipStatus: MembershipStatus,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    existing = await db[Collections.CLIENTS].find_one({"id": client_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    from datetime import datetime
    
    update_data = {
        "membership": membership,
        "membershipStatus": membershipStatus.value
    }
    if startDate:
        update_data["membershipStartDate"] = datetime.fromisoformat(startDate)
    if endDate:
        update_data["membershipEndDate"] = datetime.fromisoformat(endDate)
    
    await db[Collections.CLIENTS].update_one(
        {"id": client_id},
        {"$set": update_data}
    )
    
    updated = await db[Collections.CLIENTS].find_one({"id": client_id})
    return updated