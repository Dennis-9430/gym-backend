# Esquemas Pydantic para ventas
# Relacionado con: routers/sales.py, database.py
"""Sale Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PaymentMethod(str, Enum):
    # Métodos de pago disponibles
    CASH = "CASH"
    TRANSFER = "TRANSFER"
    DEPOSIT = "DEPOSIT"
    MIXED = "MIXED"


class PaymentStatus(str, Enum):
    # Estado del pago
    PENDING = "pending"
    VERIFIED = "verified"


class SaleItem(BaseModel):
    # Ítem individual en una venta
    # Relacionado con: routers/sales.py
    productId: Optional[str] = None
    serviceId: Optional[str] = None
    productName: str
    description: Optional[str] = None
    category: Optional[str] = None
    quantity: int = 1
    unitPrice: float
    unitDiscount: float = 0.0
    subtotal: float
    source: Optional[str] = None
    taxRate: float = 0.0


class SaleBase(BaseModel):
    # Datos base de una venta
    # Relacionado con: routers/sales.py, frontend
    tenantId: str = ""  # ID del tenant (gimnasio) al que pertenece
    items: List[SaleItem]
    subtotal: float
    tax: float = 0.0
    total: float
    paymentMethod: PaymentMethod = PaymentMethod.CASH
    paymentStatus: PaymentStatus = PaymentStatus.VERIFIED
    voucherCode: Optional[str] = None
    voucherImage: Optional[str] = None  # Imagen del comprobante (base64)
    clientId: Optional[str] = None
    clientName: Optional[str] = None
    notes: str = ""


class SaleCreate(SaleBase):
    # Datos para crear venta
    # Relacionado con: routers/sales.py (create_sale)
    generateInvoice: bool = False
    cashAmount: float = 0.0
    transferAmount: float = 0.0
    clientDocument: Optional[str] = None
    clientFirstName: Optional[str] = None
    clientLastName: Optional[str] = None
    clientEmail: Optional[str] = None
    clientPhone: Optional[str] = None
    clientAddress: Optional[str] = None
    invoiceEmail: Optional[str] = None


class SaleResponse(SaleBase):
    # Respuesta con todos los datos de la venta
    # Relacionado con: routers/sales.py (get_sale)
    id: str
    createdBy: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    cashAmount: float = 0.0
    transferAmount: float = 0.0
    clientFirstName: Optional[str] = None
    clientLastName: Optional[str] = None
    clientDocument: Optional[str] = None
    clientEmail: Optional[str] = None
    clientPhone: Optional[str] = None
    clientAddress: Optional[str] = None
    generateInvoice: bool = False
    invoiceEmail: Optional[str] = None

    class Config:
        populate_by_name = True
        from_attributes = True


class SaleUpdate(BaseModel):
    # Datos para actualizar método de pago de una venta
    # Relacionado con: routers/sales.py (update_sale)
    paymentMethod: PaymentMethod
    cashAmount: float = 0.0
    transferAmount: float = 0.0


class SaleListResponse(BaseModel):
    # Lista de ventas con paginación
    # Relacionado con: routers/sales.py (list_sales)
    sales: List[SaleResponse]
    total: int
    page: int = 1
    limit: int = 50