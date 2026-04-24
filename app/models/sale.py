# Esquemas Pydantic para ventas
# Relacionado con: routers/sales.py, database.py
"""Sale Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PaymentMethod(str, Enum):
    # Métodos de pago disponibles
    # Relacionado con: routers/sales.py, frontend
    CASH = "CASH"
    CARD = "CARD"
    TRANSFER = "TRANSFER"


class SaleItem(BaseModel):
    # Ítem individual en una venta
    # Relacionado con: routers/sales.py
    productId: Optional[str] = None
    serviceId: Optional[str] = None
    productName: str
    quantity: int = 1
    unitPrice: float
    subtotal: float


class SaleBase(BaseModel):
    # Datos base de una venta
    # Relacionado con: routers/sales.py, frontend
    tenantId: str = ""  # ID del tenant (gimnasio) al que pertenece
    items: List[SaleItem]
    subtotal: float
    tax: float = 0.0
    total: float
    paymentMethod: PaymentMethod = PaymentMethod.CASH
    clientId: Optional[int] = None
    clientName: Optional[str] = None
    notes: str = ""


class SaleCreate(SaleBase):
    # Datos para crear venta
    # Relacionado con: routers/sales.py (create_sale)
    pass


class SaleResponse(SaleBase):
    # Respuesta con todos los datos de la venta
    # Relacionado con: routers/sales.py (get_sale)
    id: str = Field(..., alias="_id")
    createdBy: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class SaleListResponse(BaseModel):
    # Lista de ventas con paginación
    # Relacionado con: routers/sales.py (list_sales)
    sales: List[SaleResponse]
    total: int