# Endpoints para gestión de productos
# Relacionado con: models/product.py, auth/router.py, database.py
"""Products router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from typing import Optional
from bson import ObjectId
from app.models.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.api.dependencies import get_tenant_from_request
from app.database import get_database, Collections
from app.utils.sanitize import sanitize_search_input
from app.utils.demo_protect import check_seed_protected
from app.config import settings


router = APIRouter(prefix="/api/products", tags=["Products"])


def serialize_product(doc: dict) -> dict:
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
    return doc


@router.get("", response_model=ProductListResponse)
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = Query(False),
    tenant: dict = Depends(get_tenant_from_request)
):
    db = get_database()
    
    query = {"tenantId": tenant["tenantId"]}
    if category:
        query["category"] = category
    
    # Sanitizar búsqueda - búsqueda exacta
    sanitized = sanitize_search_input(search)
    if sanitized:
        query["$or"] = [
            {"name": sanitized},
            {"code": sanitized}
        ]
    if low_stock:
        query["$expr"] = {"$lte": ["$stock", "$minStock"]}
    
    total = await db[Collections.PRODUCTS].count_documents(query)
    cursor = db[Collections.PRODUCTS].find(query).skip(skip).limit(limit)
    products = await cursor.to_list(length=limit)
    
    return {
        "products": [serialize_product(p) for p in products],
        "total": total,
        "page": skip // limit + 1,
        "limit": limit,
    }


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    tenant: dict = Depends(get_tenant_from_request)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    # SEGURIDAD: filtrar por tenantId para evitar fuga entre negocios
    product = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id), "tenantId": tenant["tenantId"]})
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return serialize_product(product)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    tenant: dict = Depends(get_tenant_from_request)
):
    db = get_database()
    
    existing = await db[Collections.PRODUCTS].find_one({"code": product_data.code, "tenantId": tenant["tenantId"]})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un producto con el código '{product_data.code}'"
        )
    
    product_doc = product_data.model_dump()
    product_doc["tenantId"] = tenant["tenantId"]
    product_doc["createdAt"] = None
    product_doc["updatedAt"] = None
    
    result = await db[Collections.PRODUCTS].insert_one(product_doc)
    product_doc["_id"] = result.inserted_id
    
    return serialize_product(product_doc)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    tenant: dict = Depends(get_tenant_from_request)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    # SEGURIDAD: filtrar por tenantId para evitar fuga entre negocios
    existing = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id), "tenantId": tenant["tenantId"]})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant["tenantId"], Collections.PRODUCTS, product_id, "modificados")
    
    update_data = {k: v for k, v in product_data.model_dump().items() if v is not None}
    
    # Validar código único si se está actualizando
    if "code" in update_data:
        code_exists = await db[Collections.PRODUCTS].find_one(
            {"code": update_data["code"], "tenantId": tenant["tenantId"], "_id": {"$ne": ObjectId(product_id)}}
        )
        if code_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe otro producto con el código '{update_data['code']}'"
            )
    
    if update_data:
        await db[Collections.PRODUCTS].update_one(
            {"_id": ObjectId(product_id), "tenantId": tenant["tenantId"]},
            {"$set": update_data}
        )
    
    # SEGURIDAD: read-back también filtra por tenantId
    updated = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id), "tenantId": tenant["tenantId"]})
    return serialize_product(updated)


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    tenant: dict = Depends(get_tenant_from_request)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant["tenantId"], Collections.PRODUCTS, product_id, "eliminados")
    
    result = await db[Collections.PRODUCTS].delete_one({
        "_id": ObjectId(product_id),
        "tenantId": tenant["tenantId"]
    })
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return Response(status_code=204)


@router.put("/{product_id}/stock")
async def update_stock(
    product_id: str,
    quantity: int,
    operation: str = "add",
    tenant: dict = Depends(get_tenant_from_request)
):
    db = get_database()
    
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    # SEGURIDAD: filtrar por tenantId para evitar fuga entre negocios
    existing = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id), "tenantId": tenant["tenantId"]})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant["tenantId"], Collections.PRODUCTS, product_id, "modificados")
    
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
        {"_id": ObjectId(product_id), "tenantId": tenant["tenantId"]},
        {"$set": {"stock": new_stock}}
    )
    
    # SEGURIDAD: read-back también filtra por tenantId
    updated = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id), "tenantId": tenant["tenantId"]})
    return serialize_product(updated)
