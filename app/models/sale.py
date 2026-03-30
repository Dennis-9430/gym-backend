"""Sale Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PaymentMethod(str, Enum):
    CASH = "CASH"
    CARD = "CARD"
    TRANSFER = "TRANSFER"


class SaleItem(BaseModel):
    productId: Optional[str] = None
    serviceId: Optional[str] = None
    productName: str
    quantity: int = 1
    unitPrice: float
    subtotal: float


class SaleBase(BaseModel):
    items: List[SaleItem]
    subtotal: float
    tax: float = 0.0
    total: float
    paymentMethod: PaymentMethod = PaymentMethod.CASH
    clientId: Optional[int] = None
    clientName: Optional[str] = None
    notes: str = ""


class SaleCreate(SaleBase):
    pass


class SaleResponse(SaleBase):
    id: str = Field(..., alias="_id")
    createdBy: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class SaleListResponse(BaseModel):
    sales: List[SaleResponse]
    total: int