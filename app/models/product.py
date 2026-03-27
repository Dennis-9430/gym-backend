"""Product Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProductBase(BaseModel):
    code: str
    name: str
    description: str = ""
    category: str = "General"
    unitPrice: float = 0.0
    stock: int = 0
    minStock: int = 0


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unitPrice: Optional[float] = None
    stock: Optional[int] = None
    minStock: Optional[int] = None


class ProductResponse(ProductBase):
    id: str = Field(..., alias="_id")
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    total: int