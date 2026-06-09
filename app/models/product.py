# Esquemas Pydantic para productos
# Relacionado con: routers/products.py, database.py
"""Product Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProductBase(BaseModel):
    # Datos base del producto
    tenantId: str = ""
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=300)
    category: str = Field(default="General", max_length=50)
    unitPrice: float = Field(default=0.0, ge=0)
    taxRate: float = Field(default=0.0, ge=0, le=100)
    stock: int = Field(default=0, ge=0)
    minStock: int = Field(default=0, ge=0)


class ProductCreate(ProductBase):
    # Datos para crear producto
    # Relacionado con: routers/products.py (create_product)
    pass


class ProductUpdate(BaseModel):
    # Datos para actualizar producto
    # Relacionado con: routers/products.py (update_product)
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unitPrice: Optional[float] = None
    taxRate: Optional[float] = None
    stock: Optional[int] = None
    minStock: Optional[int] = None


class ProductResponse(ProductBase):
    # Respuesta con todos los datos del producto
    # Relacionado con: routers/products.py (get_product)
    id: str
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ProductListResponse(BaseModel):
    # Lista de productos con paginación
    # Relacionado con: routers/products.py (list_products)
    products: list[ProductResponse]
    total: int
    page: int = 1
    limit: int = 50