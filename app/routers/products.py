# Endpoints para gestión de productos
# Relacionado con: models/product.py, auth/router.py, database.py
"""Products router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from typing import Optional
from bson import ObjectId
from jose import JWTError, jwt
from app.models.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse
)
from app.models.tenant import TenantResponse, SubscriptionPlan, SubscriptionStatus
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections
from app.utils.sanitize import sanitize_search_input
from app.config import settings


router = APIRouter(prefix="/api/products", tags=["Products"])


def serialize_product(doc: dict) -> dict:
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def get_tenant_from_header_products(authorization: str = Header(None)) -> TenantResponse:
    """Extrae el tenant del token JWT"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )
    
    token = authorization.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id = payload.get("tenantId")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido"
            )
        
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
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )


@router.get("", response_model=ProductListResponse)
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = Query(False),
    tenant: TenantResponse = Depends(get_tenant_from_header_products)
):
    db = get_database()
    
    query = {"tenantId": tenant.tenantId}
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
        "total": total
    }


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    tenant: TenantResponse = Depends(get_tenant_from_header_products)
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
    tenant: TenantResponse = Depends(get_tenant_from_header_products)
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
    tenant: TenantResponse = Depends(get_tenant_from_header_products)
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
    tenant: TenantResponse = Depends(get_tenant_from_header_products)
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
    tenant: TenantResponse = Depends(get_tenant_from_header_products)
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