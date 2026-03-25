"""Clients router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from bson import ObjectId
from app.models.client import (
    ClientCreate, ClientUpdate, ClientResponse, 
    ClientListResponse, MembershipStatus
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections


router = APIRouter(prefix="/api/clients", tags=["Clients"])


def serialize_client(doc: dict) -> dict:
    if doc:
        doc["_id"] = doc.get("id", doc["_id"]) if "_id" in doc else doc.get("id", 0)
    return doc


@router.get("", response_model=ClientListResponse)
async def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[MembershipStatus] = None,
    search: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    query = {}
    if status:
        query["membershipStatus"] = status.value
    if search:
        query["$or"] = [
            {"firstName": {"$regex": search, "$options": "i"}},
            {"lastName": {"$regex": search, "$options": "i"}},
            {"documentNumber": {"$regex": search, "$options": "i"}}
        ]
    
    total = await db[Collections.CLIENTS].count_documents(query)
    cursor = db[Collections.CLIENTS].find(query).skip(skip).limit(limit)
    clients = await cursor.to_list(length=limit)
    
    return {"clients": clients, "total": total}


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    client = await db[Collections.CLIENTS].find_one({"id": client_id})
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    return client


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_data: ClientCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    existing = await db[Collections.CLIENTS].find_one(
        {"documentNumber": client_data.documentNumber}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client with this document number already exists"
        )
    
    last_client = await db[Collections.CLIENTS].find_one(sort=[("id", -1)])
    next_id = (last_client["id"] + 1) if last_client else 1
    
    client_doc = client_data.model_dump()
    client_doc["id"] = next_id
    client_doc["createdAt"] = None
    client_doc["membershipStartDate"] = None
    client_doc["membershipEndDate"] = None
    
    result = await db[Collections.CLIENTS].insert_one(client_doc)
    
    return {**client_doc, "_id": next_id}


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    client_data: ClientUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    existing = await db[Collections.CLIENTS].find_one({"id": client_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    update_data = {k: v for k, v in client_data.model_dump().items() if v is not None}
    
    if update_data:
        await db[Collections.CLIENTS].update_one(
            {"id": client_id},
            {"$set": update_data}
        )
    
    updated = await db[Collections.CLIENTS].find_one({"id": client_id})
    return updated


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    result = await db[Collections.CLIENTS].delete_one({"id": client_id})
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
    current_user: UserResponse = Depends(get_current_user)
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