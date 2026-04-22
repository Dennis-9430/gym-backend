# Endpoints para gestión de ventas
# Relacionado con: models/sale.py, auth/router.py, database.py
"""Sales router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from datetime import datetime
from bson import ObjectId
from app.models.sale import (
    SaleCreate, SaleResponse, SaleListResponse, SaleItem
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections


router = APIRouter(prefix="/api/sales", tags=["Sales"])


def serialize_sale(doc: dict) -> dict:
    # Convierte documento MongoDB a respuesta JSON
    # Relacionado con: models/sale.py
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.get("", response_model=SaleListResponse)
async def list_sales(
    # Lista ventas con paginación y filtros por fecha
    # Relacionado con: models/sale.py (SaleListResponse), frontend
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    client_id: Optional[int] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    query = {}
    if start_date:
        query["createdAt"] = {"$gte": datetime.fromisoformat(start_date)}
    if end_date:
        if "createdAt" in query:
            query["createdAt"]["$lte"] = datetime.fromisoformat(end_date)
        else:
            query["createdAt"] = {"$lte": datetime.fromisoformat(end_date)}
    if client_id:
        query["clientId"] = client_id
    
    total = await db[Collections.SALES].count_documents(query)
    cursor = db[Collections.SALES].find(query).sort("createdAt", -1).skip(skip).limit(limit)
    sales = await cursor.to_list(length=limit)
    
    return {
        "sales": [serialize_sale(s) for s in sales],
        "total": total
    }


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale ID"
        )
    
    sale = await db[Collections.SALES].find_one({"_id": ObjectId(sale_id)})
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    return serialize_sale(sale)


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(
    sale_data: SaleCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    sale_doc = sale_data.model_dump()
    sale_doc["createdBy"] = current_user.username
    sale_doc["createdAt"] = datetime.utcnow()
    
    for item in sale_doc.get("items", []):
        if item.get("productId"):
            product = await db[Collections.PRODUCTS].find_one(
                {"_id": ObjectId(item["productId"])}
            )
            if product:
                new_stock = product.get("stock", 0) - item.get("quantity", 1)
                await db[Collections.PRODUCTS].update_one(
                    {"_id": ObjectId(item["productId"])},
                    {"$set": {"stock": new_stock}}
                )
    
    result = await db[Collections.SALES].insert_one(sale_doc)
    sale_doc["_id"] = str(result.inserted_id)
    
    return sale_doc


@router.delete("/{sale_id}")
async def delete_sale(
    sale_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    if current_user.role.value != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete sales"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale ID"
        )
    
    result = await db[Collections.SALES].delete_one({"_id": ObjectId(sale_id)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    return {"message": "Sale deleted successfully"}