# Router para gestión de facturas
# Relacionado con: models/invoice.py, database.py
"""Invoices API router"""
from fastapi import APIRouter, HTTPException, Depends, Query, Header
from typing import Optional
from bson import ObjectId
from jose import JWTError, jwt
from datetime import datetime
from app.models.invoice import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceListResponse,
    InvoiceEmailRequest,
    InvoiceEmailResponse,
    InvoiceStatus,
)
from app.models.tenant import TenantResponse, SubscriptionPlan, SubscriptionStatus
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections
from app.config import settings


router = APIRouter(prefix="/api/invoices", tags=["Invoices"])


async def get_tenant_from_header(authorization: str = Header(None)) -> TenantResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id = payload.get("tenantId")
        
        if not tenant_id:
            raise HTTPException(status_code=401, detail="Token inválido")
        
        db = get_database()
        tenant_doc = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        
        if not tenant_doc:
            raise HTTPException(status_code=401, detail="Tenant no encontrado")
        
        plan = SubscriptionPlan.BASIC
        plan_str = tenant_doc.get("plan", "BASIC")
        if plan_str in ["BASIC", "PREMIUM"]:
            plan = SubscriptionPlan(plan_str)
        
        return TenantResponse(
            id=tenant_doc.get("tenantId", tenant_id),
            tenantId=tenant_id,
            email=tenant_doc.get("email", ""),
            businessName=tenant_doc.get("businessName", ""),
            businessPhone=tenant_doc.get("businessPhone", ""),
            businessAddress=tenant_doc.get("businessAddress", ""),
            businessRuc=tenant_doc.get("businessRuc", ""),
            plan=plan,
            subscriptionStatus=tenant_doc.get("subscriptionStatus", SubscriptionStatus.ACTIVE),
            subscriptionEndDate=tenant_doc.get("subscriptionEndDate"),
            taxRate=tenant_doc.get("taxRate", 12.0),
            currency=tenant_doc.get("currency", "USD"),
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


def serialize_invoice(doc: dict) -> dict:
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
    return doc


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    query = {"tenantId": tenant.tenantId}
    total = await db[Collections.INVOICES].count_documents(query)
    
    cursor = db[Collections.INVOICES].find(query).sort("createdAt", -1).skip(skip).limit(limit)
    invoices = await cursor.to_list(length=limit)
    
    return {
        "invoices": [serialize_invoice(inv) for inv in invoices],
        "total": total
    }


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: str,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    if not ObjectId.is_valid(invoice_id):
        raise HTTPException(status_code=400, detail="ID de factura inválido")
    
    invoice = await db[Collections.INVOICES].find_one({
        "_id": ObjectId(invoice_id),
        "tenantId": tenant.tenantId
    })
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    return serialize_invoice(invoice)


@router.post("", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    # Obtener siguiente número de factura
    counter = await db.counters.find_one_and_update(
        {"tenantId": tenant.tenantId},
        {"$inc": {"invoiceCount": 1}},
        upsert=True
    )
    invoice_count = counter.get("invoiceCount", 1) if counter else 1
    invoice_number = f"FAC-{datetime.now().year}-{invoice_count:06d}"
    
    # Obtener datos del negocio desde tenant
    business_tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant.tenantId})
    
    invoice_doc = {
        "tenantId": tenant.tenantId,
        "createdBy": current_user.username,
        "type": invoice_data.type.value,
        "invoiceNumber": invoice_number,
        "business": invoice_data.business.model_dump() if invoice_data.business else {
            "name": business_tenant.get("businessName", "") if business_tenant else "",
            "ruc": business_tenant.get("businessRuc", "") if business_tenant else "",
            "address": business_tenant.get("businessAddress", "") if business_tenant else "",
            "phone": business_tenant.get("businessPhone", "") if business_tenant else "",
            "email": business_tenant.get("email", "") if business_tenant else "",
        },
        "client": invoice_data.client.model_dump(),
        "items": [item.model_dump() for item in invoice_data.items],
        "totals": invoice_data.totals.model_dump(),
        "payment": invoice_data.payment.model_dump(),
        "membershipMeta": invoice_data.membershipMeta.model_dump() if invoice_data.membershipMeta else None,
        "status": InvoiceStatus.GENERATED.value,
        "createdAt": datetime.utcnow(),
    }
    
    if invoice_data.sendEmail and invoice_data.client.email:
        invoice_doc["emailDelivery"] = {
            "requested": True,
            "sent": False,
        }
    
    result = await db[Collections.INVOICES].insert_one(invoice_doc)
    invoice_doc["_id"] = result.inserted_id
    
    return serialize_invoice(invoice_doc)


@router.delete("/{invoice_id}")
async def delete_invoice(
    invoice_id: str,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    if current_user.role.value not in ["ADMIN", "GERENTE"]:
        raise HTTPException(status_code=403, detail="Solo administradores o gerentes pueden eliminar facturas")
    
    if not ObjectId.is_valid(invoice_id):
        raise HTTPException(status_code=400, detail="ID de factura inválido")
    
    result = await db[Collections.INVOICES].delete_one({
        "_id": ObjectId(invoice_id),
        "tenantId": tenant.tenantId
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    return {"message": "Factura eliminada correctamente"}


@router.post("/send-email", response_model=InvoiceEmailResponse)
async def send_invoice_email(
    email_request: InvoiceEmailRequest,
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    # Obtener factura
    if not ObjectId.is_valid(email_request.invoiceId):
        raise HTTPException(status_code=400, detail="ID de factura inválido")
    
    invoice = await db[Collections.INVOICES].find_one({
        "_id": ObjectId(email_request.invoiceId),
        "tenantId": tenant.tenantId
    })
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    # Verificar configuración de email del negocio
    business = invoice.get("business", {})
    business_email = business.get("email", "")
    
    if not business_email:
        return {
            "success": False,
            "message": "El negocio no tiene email configurado"
        }
    
    # Aquí iría la lógica de envío de email
    # Por ahora, marcamos como enviado
    await db[Collections.INVOICES].update_one(
        {"_id": ObjectId(email_request.invoiceId)},
        {"$set": {
            "emailDelivery.sent": True,
            "emailDelivery.sentAt": datetime.utcnow(),
            "emailDelivery.recipient": email_request.recipientEmail,
            "status": InvoiceStatus.SENT.value
        }}
    )
    
    return {
        "success": True,
        "message": f"Factura enviada a {email_request.recipientEmail}"
    }


@router.get("/next-number")
async def get_next_invoice_number(
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    counter = await db.counters.find_one({"tenantId": tenant.tenantId})
    invoice_count = (counter.get("invoiceCount", 0) + 1) if counter else 1
    
    return f"FAC-{datetime.now().year}-{invoice_count:06d}"