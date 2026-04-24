# Esquemas Pydantic para productos
# Relacionado con: routers/products.py, database.py
"""Product Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProductBase(BaseModel):
    # Datos base del producto
    # Relacionado con: routers/products.py, frontend
    tenantId: str = ""  # ID del tenant (gimnasio) al que pertenece
    code: str
    name: str
    description: str = ""
    category: str = "General"
    unitPrice: float = 0.0
    stock: int = 0
    minStock: int = 0


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
    stock: Optional[int] = None
    minStock: Optional[int] = None


class ProductResponse(ProductBase):
    # Respuesta con todos los datos del producto
    # Relacionado con: routers/products.py (get_product)
    id: str = Field(..., alias="_id")
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ProductListResponse(BaseModel):
    # Lista de productos con paginación
    # Relacionado con: routers/products.py (list_products)
    products: list[ProductResponse]
    total: int