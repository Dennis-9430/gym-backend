# Router para gestión de facturas
# Relacionado con: models/invoice.py, database.py
"""Invoices API router"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, Request, Response
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
from app.auth.cookie import get_token_from_request
from app.database import get_database, Collections
from app.utils.demo_protect import check_seed_protected
from app.config import settings
from app.services.email import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invoices", tags=["Invoices"])


async def get_tenant_from_header(request: Request) -> TenantResponse:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    
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
        "total": total,
        "page": skip // limit + 1,
        "limit": limit,
    }


@router.get("/next-number")
async def get_next_invoice_number(
    tenant: TenantResponse = Depends(get_tenant_from_header)
):
    db = get_database()
    
    counter = await db.counters.find_one({"tenantId": tenant.tenantId})
    invoice_count = (counter.get("invoiceCount", 0) + 1) if counter else 1
    
    return f"FAC-{datetime.now().year}-{invoice_count:06d}"


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
    
    # Obtener siguiente número de factura (con return_document=AFTER para evitar duplicados)
    from pymongo import ReturnDocument
    counter = await db.counters.find_one_and_update(
        {"tenantId": tenant.tenantId},
        {"$inc": {"invoiceCount": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    invoice_count = counter["invoiceCount"]
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
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant.tenantId, Collections.INVOICES, invoice_id, "eliminados")
    
    result = await db[Collections.INVOICES].delete_one({
        "_id": ObjectId(invoice_id),
        "tenantId": tenant.tenantId
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    return Response(status_code=204)


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
    
    # Preparar datos para la plantilla HTML
    inv = invoice
    created_at = inv.get("createdAt", datetime.utcnow())
    if hasattr(created_at, "strftime"):
        created_at_str = created_at.strftime("%d/%m/%Y %H:%M")
    else:
        created_at_str = str(created_at)

    biz = inv.get("business", {})
    client = inv.get("client", {})
    totals = inv.get("totals", {})
    payment = inv.get("payment", {})

    payment_labels = {"CASH": "Efectivo", "TRANSFER": "Transferencia", "MIXED": "Mixto"}
    payment_method = payment_labels.get(payment.get("method", ""), payment.get("method", ""))

    # Construir filas de items
    items_rows = "".join(
        f"""<tr>
            <td style="padding: 6px 12px; border-bottom: 1px solid #f3f4f6; font-size: 13px;">{item.get("code", "")}</td>
            <td style="padding: 6px 12px; border-bottom: 1px solid #f3f4f6; font-size: 13px;">{item.get("name", "")}</td>
            <td style="padding: 6px 12px; border-bottom: 1px solid #f3f4f6; font-size: 13px; text-align: center;">{item.get("quantity", 0)}</td>
            <td style="padding: 6px 12px; border-bottom: 1px solid #f3f4f6; font-size: 13px; text-align: right;">${item.get("unitPrice", 0):.2f}</td>
            <td style="padding: 6px 12px; border-bottom: 1px solid #f3f4f6; font-size: 13px; text-align: right;">{item.get("discount", 0):.2f}</td>
            <td style="padding: 6px 12px; border-bottom: 1px solid #f3f4f6; font-size: 13px; text-align: right;">${item.get("subtotal", 0):.2f}</td>
        </tr>"""
        for item in inv.get("items", [])
    )

    subject = f"Factura {inv.get('invoiceNumber', '')} — {biz.get('name', '')}"
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; padding: 24px; background: #f4f4f5; margin: 0;">
    <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; padding: 32px;">
        <!-- Header -->
        <div style="border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 24px;">
            <h2 style="color: #1f2937; margin: 0 0 4px 0;">{biz.get("name", "")}</h2>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">RUC: {biz.get("ruc", "")}</p>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">
                {biz.get("address", "")} | Tel: {biz.get("phone", "")} | {biz.get("email", "")}
            </p>
        </div>

        <!-- Invoice info + Client -->
        <div style="display: flex; justify-content: space-between; margin-bottom: 24px;">
            <div>
                <h3 style="color: #374151; margin: 0 0 8px 0; font-size: 18px;">Factura N° {inv.get("invoiceNumber", "")}</h3>
                <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Fecha: {created_at_str}</p>
            </div>
            <div style="text-align: right;">
                <h4 style="color: #374151; margin: 0 0 8px 0; font-size: 14px;">Cliente</h4>
                <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">{client.get("firstName", "")} {client.get("lastName", "")}</p>
                <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Doc: {client.get("documentNumber", "")}</p>
                <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">{client.get("email", "")}</p>
            </div>
        </div>

        <!-- Items table -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
            <thead>
                <tr style="background: #f3f4f6;">
                    <th style="padding: 8px 12px; text-align: left; font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">Código</th>
                    <th style="padding: 8px 12px; text-align: left; font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">Descripción</th>
                    <th style="padding: 8px 12px; text-align: center; font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">Cant.</th>
                    <th style="padding: 8px 12px; text-align: right; font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">Precio Unit.</th>
                    <th style="padding: 8px 12px; text-align: right; font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">Dto.</th>
                    <th style="padding: 8px 12px; text-align: right; font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                {items_rows}
            </tbody>
        </table>

        <!-- Totals -->
        <div style="border-top: 2px solid #e5e7eb; padding-top: 16px; margin-bottom: 24px;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">Subtotal:</td>
                    <td style="text-align: right; padding: 4px 0; font-size: 14px; color: #374151; width: 140px;">${totals.get("subtotal", 0):.2f}</td>
                </tr>
                <tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">Descuento:</td>
                    <td style="text-align: right; padding: 4px 0; font-size: 14px; color: #dc2626; width: 140px;">${totals.get("discountAmount", 0):.2f}</td>
                </tr>
                {"".join(f'''<tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">ICE:</td>
                    <td style="text-align: right; padding: 4px 0; font-size: 14px; color: #374151; width: 140px;">${totals.get("iceAmount", 0):.2f}</td>
                </tr>''' for _ in [1] if totals.get("iceAmount", 0) > 0)}
                <tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">IVA ({totals.get("taxAmount", 0)  / totals.get("subtotal", 1) * 100:.0f}%):</td>
                    <td style="text-align: right; padding: 4px 0; font-size: 14px; color: #374151; width: 140px;">${totals.get("taxAmount", 0):.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 12px;"></td>
                    <td style="border-top: 2px solid #2563eb; padding: 8px 0;"></td>
                </tr>
                <tr>
                    <td style="text-align: right; padding: 8px 12px; font-size: 18px; font-weight: bold; color: #1f2937;">Total:</td>
                    <td style="text-align: right; padding: 8px 0; font-size: 18px; font-weight: bold; color: #2563eb; width: 140px;">${totals.get("total", 0):.2f}</td>
                </tr>
            </table>
        </div>

        <!-- Payment info -->
        <div style="background: #f9fafb; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
            <h4 style="color: #374151; margin: 0 0 8px 0; font-size: 14px;">Información de pago</h4>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Método: {payment_method}</p>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Efectivo: ${payment.get("cashAmount", 0):.2f}</p>
            {"".join(f'<p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Transferencia: ${payment.get("transferAmount", 0):.2f}</p>' for _ in [1] if payment.get("transferAmount", 0) > 0)}
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Pagado: <strong>${payment.get("paid", 0):.2f}</strong></p>
            {"".join(f'<p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Cambio: ${payment.get("change", 0):.2f}</p>' for _ in [1] if payment.get("change", 0) > 0)}
        </div>

        <!-- Footer -->
        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0 16px 0;">
        <p style="color: #9ca3af; font-size: 12px; text-align: center; margin: 0;">
            {biz.get("name", "")} — {biz.get("address", "")}<br>
            Tel: {biz.get("phone", "")} | Email: {biz.get("email", "")}
        </p>
    </div>
</body>
</html>"""

    text = (
        f"Factura {inv.get('invoiceNumber', '')} — {biz.get('name', '')}\n\n"
        f"Cliente: {client.get('firstName', '')} {client.get('lastName', '')}\n"
        f"Total: ${totals.get('total', 0):.2f}\n\n"
        f"Gracias por su preferencia."
    )

    try:
        success = await send_email(
            to=email_request.recipientEmail,
            subject=subject,
            html=html,
            text=text,
        )

        if success:
            await db[Collections.INVOICES].update_one(
                {
                    "_id": ObjectId(email_request.invoiceId),
                    "tenantId": tenant.tenantId
                },
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
        else:
            raise Exception("send_email returned False")

    except Exception as e:
        logger.error("Error enviando factura %s a %s: %s", inv.get("invoiceNumber", ""), email_request.recipientEmail, e)

        await db[Collections.INVOICES].update_one(
            {
                "_id": ObjectId(email_request.invoiceId),
                "tenantId": tenant.tenantId
            },
            {"$set": {
                "emailDelivery.sent": False,
                "emailDelivery.errorMessage": str(e),
                "status": InvoiceStatus.FAILED.value
            }}
        )
        return {
            "success": False,
            "message": "Error al enviar la factura. Intente nuevamente."
        }
