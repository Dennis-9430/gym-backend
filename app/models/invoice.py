# Esquemas Pydantic para facturas
# Relacionado con: routers/invoices.py, database.py
"""Invoice Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class InvoiceType(str, Enum):
    MEMBERSHIP = "MEMBERSHIP"
    PRODUCT = "PRODUCT"


class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    SENT = "SENT"
    FAILED = "FAILED"


class PaymentMethodType(str, Enum):
    CASH = "CASH"
    TRANSFER = "TRANSFER"
    MIXED = "MIXED"


class InvoiceBusiness(BaseModel):
    name: str
    ruc: str
    address: str
    phone: str
    email: str


class InvoiceClient(BaseModel):
    documentNumber: str
    firstName: str
    lastName: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None


class InvoiceItem(BaseModel):
    id: Optional[int] = None
    code: Optional[str] = None
    name: str
    category: Optional[str] = None
    quantity: int = 1
    unitPrice: float
    discount: float = 0.0
    subtotal: float


class InvoiceTotals(BaseModel):
    subtotal: float
    discountAmount: float = 0.0
    taxAmount: float = 0.0
    iceAmount: float = 0.0
    total: float


class InvoicePayment(BaseModel):
    method: PaymentMethodType = PaymentMethodType.CASH
    cashAmount: float = 0.0
    transferAmount: float = 0.0
    voucherCode: Optional[str] = None
    paid: float
    change: float = 0.0


class InvoiceMembershipMeta(BaseModel):
    serviceName: str
    serviceId: Optional[str] = None
    startDate: str
    endDate: Optional[str] = None
    status: str = "PAID"


class InvoiceEmailDelivery(BaseModel):
    requested: bool = False
    sent: bool = False
    sentAt: Optional[datetime] = None
    recipient: Optional[str] = None
    errorMessage: Optional[str] = None


class InvoiceBase(BaseModel):
    tenantId: str = ""
    type: InvoiceType
    invoiceNumber: str
    business: InvoiceBusiness
    client: InvoiceClient
    items: List[InvoiceItem]
    totals: InvoiceTotals
    payment: InvoicePayment
    membershipMeta: Optional[InvoiceMembershipMeta] = None
    emailDelivery: Optional[InvoiceEmailDelivery] = None
    status: InvoiceStatus = InvoiceStatus.GENERATED


class InvoiceCreate(InvoiceBase):
    sendEmail: bool = False


class InvoiceResponse(InvoiceBase):
    id: str = Field(..., alias="_id")
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class InvoiceListResponse(BaseModel):
    invoices: List[InvoiceResponse]
    total: int


class InvoiceEmailRequest(BaseModel):
    invoiceId: str
    recipientEmail: str


class InvoiceEmailResponse(BaseModel):
    success: bool
    message: str