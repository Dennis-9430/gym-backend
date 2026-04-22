# Endpoints para gestión de productos
# Relacionado con: models/product.py, auth/router.py, database.py
"""Products router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from bson import ObjectId
from app.models.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections


router = APIRouter(prefix="/api/products", tags=["Products"])


def serialize_product(doc: dict) -> dict:
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.get("", response_model=ProductListResponse)
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = Query(False),
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    query = {}
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"code": {"$regex": search, "$options": "i"}}
        ]
    if low_stock:
        query["$expr"] = {"$lte": ["$stock", "$minStock"]}
    
    total = await db[Collections.PRODUCTS].count_documents(query)
    cursor = db[Collections.PRODUCTS].find(query).skip(skip).limit(limit)
    products = await cursor.to_list(length=limit)
    
    return {
        "products": [serialize_product(p) for p in products],
        "total": total
    }


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    product = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return serialize_product(product)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    existing = await db[Collections.PRODUCTS].find_one({"code": product_data.code})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product with this code already exists"
        )
    
    product_doc = product_data.model_dump()
    product_doc["createdAt"] = None
    product_doc["updatedAt"] = None
    
    result = await db[Collections.PRODUCTS].insert_one(product_doc)
    product_doc["_id"] = str(result.inserted_id)
    
    return product_doc


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    existing = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id)})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    update_data = {k: v for k, v in product_data.model_dump().items() if v is not None}
    
    if update_data:
        await db[Collections.PRODUCTS].update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_data}
        )
    
    updated = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id)})
    return serialize_product(updated)


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    result = await db[Collections.PRODUCTS].delete_one({"_id": ObjectId(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return {"message": "Product deleted successfully"}


@router.put("/{product_id}/stock")
async def update_stock(
    product_id: str,
    quantity: int,
    operation: str = "add",
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    existing = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id)})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    current_stock = existing.get("stock", 0)
    if operation == "add":
        new_stock = current_stock + quantity
    elif operation == "subtract":
        new_stock = current_stock - quantity
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid operation. Use 'add' or 'subtract'"
        )
    
    await db[Collections.PRODUCTS].update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"stock": new_stock}}
    )
    
    updated = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id)})
    return serialize_product(updated)