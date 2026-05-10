# Endpoints para gestión de clientes
# Relacionado con: models/client.py, auth/router.py, database.py
"""Clients router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header, Body
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
from app.utils.demo_protect import check_seed_protected
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
    # SEGURIDAD: Eliminar logs que expongan tokens
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
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id = payload.get("tenantId")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token sin tenantId"
            )
        
        # Retornar solo con los datos necesarios del tenant
        return TenantResponse(
            id=tenant_id,
            tenantId=tenant_id,
            email=payload.get("sub", "") or "tenant@example.com",
            businessName=payload.get("businessName") or "Mi Gimnasio",
            businessPhone=payload.get("businessPhone") or "",
            businessAddress=payload.get("businessAddress") or "",
            businessRuc=payload.get("businessRuc") or "",
            plan=SubscriptionPlan.BASIC,
            subscriptionStatus=SubscriptionStatus.ACTIVE
        )
    
    except JWTError:
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
    active_only: bool = Query(False),
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    # Usar tenantId del token de tenant
    query = {"tenantId": tenant.tenantId}
    
    # Si active_only es False, incluir todos los clientes
    # Si es True, filtrar solo activos
    if active_only:
        query["membershipStatus"] = {"$ne": "EXPIRED"}
    
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
    client_id: str,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    if not ObjectId.is_valid(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de cliente inválido"
        )
    
    db = get_database()
    client = await db[Collections.CLIENTS].find_one({"_id": ObjectId(client_id), "tenantId": tenant.tenantId})
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    return ClientResponse(**serialize_client(client))


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
    
    client_doc = client_data.model_dump()
    client_doc["tenantId"] = tenant.tenantId
    client_doc["createdAt"] = None
    client_doc["membershipStartDate"] = None
    client_doc["membershipEndDate"] = None
    
    result = await db[Collections.CLIENTS].insert_one(client_doc)
    client_doc["_id"] = str(result.inserted_id)
    
    return serialize_client(client_doc)


@router.put("/update", response_model=ClientResponse)
async def update_client(
    # Actualiza un cliente existente
    # El client_id se envía en el body para evitar problemas de tipado en el path parameter
    # Relacionado con: models/client.py (ClientUpdate)
    client_data: ClientUpdate,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    client_id = client_data.client_id
    if not client_id or not ObjectId.is_valid(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de cliente inválido"
        )
    
    db = get_database()
    
    existing = await db[Collections.CLIENTS].find_one({"_id": ObjectId(client_id), "tenantId": tenant.tenantId})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant.tenantId, Collections.CLIENTS, client_id, "modificados")
    
    update_data = {k: v for k, v in client_data.model_dump().items() if v is not None and k != "client_id"}
    
    if update_data:
        await db[Collections.CLIENTS].update_one(
            {"_id": ObjectId(client_id), "tenantId": tenant.tenantId},
            {"$set": update_data}
        )
    
    updated = await db[Collections.CLIENTS].find_one({"_id": ObjectId(client_id), "tenantId": tenant.tenantId})
    return ClientResponse(**serialize_client(updated))


@router.delete("/{client_id}")
async def delete_client(
    client_id: str,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    if not ObjectId.is_valid(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de cliente inválido"
        )
    
    db = get_database()
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant.tenantId, Collections.CLIENTS, client_id, "eliminados")
    
    result = await db[Collections.CLIENTS].delete_one({"_id": ObjectId(client_id), "tenantId": tenant.tenantId})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    return {"message": "Client deleted successfully"}


@router.put("/{client_id}/membership", response_model=ClientResponse)
async def update_membership(
    client_id: str,
    membership: str,
    membershipStatus: MembershipStatus,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    if not ObjectId.is_valid(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de cliente inválido"
        )
    
    db = get_database()
    
    existing = await db[Collections.CLIENTS].find_one({"_id": ObjectId(client_id)})
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
        {"_id": ObjectId(client_id)},
        {"$set": update_data}
    )
    
    updated = await db[Collections.CLIENTS].find_one({"_id": ObjectId(client_id)})
    return ClientResponse(**serialize_client(updated))


@router.post("/{client_id}/assign-membership", response_model=ClientResponse)
async def assign_membership_with_service(
    client_id: str,
    serviceId: str = Body(...),
    startDate: Optional[str] = Body(None),
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    """
    Asigna una membresía a un cliente calculando automáticamente la fecha fin
    basándose en la duración del servicio.
    """
    db = get_database()
    from datetime import datetime, timedelta
    
    # Buscar cliente por _id de MongoDB
    existing = await db[Collections.CLIENTS].find_one({"_id": ObjectId(client_id), "tenantId": tenant.tenantId})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado"
        )
    
    # Buscar servicio
    if not ObjectId.is_valid(serviceId):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de servicio inválido"
        )
    
    service = await db[Collections.SERVICES].find_one({
        "_id": ObjectId(serviceId),
        "tenantId": tenant.tenantId
    })
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Servicio no encontrado"
        )
    
    # Calcular fechas
    start = datetime.fromisoformat(startDate) if startDate else datetime.utcnow()
    
    # Calcular fecha fin según duración
    duration = service.get("duration", 30)
    duration_unit = service.get("durationUnit", "days")
    
    if duration_unit == "days":
        end = start + timedelta(days=duration)
    elif duration_unit == "weeks":
        end = start + timedelta(weeks=duration)
    elif duration_unit == "months":
        # Agregar meses correctamente manejando fin de mes
        year = start.year
        month = start.month + duration
        day = start.day
        while month > 12:
            year += 1
            month -= 12
        # Ajustar día si el mes no tiene suficientes días
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        if day > max_day:
            day = max_day
        end = start.replace(year=year, month=month, day=day)
    else:
        end = start + timedelta(days=duration)
    
    # Actualizar cliente
    update_data = {
        "membership": service.get("name"),
        "membershipStatus": MembershipStatus.ACTIVE.value,
        "membershipStartDate": start,
        "membershipEndDate": end
    }
    
    await db[Collections.CLIENTS].update_one(
        {"_id": ObjectId(client_id)},
        {"$set": update_data}
    )
    
    updated = await db[Collections.CLIENTS].find_one({"_id": ObjectId(client_id)})
    return serialize_client(updated)