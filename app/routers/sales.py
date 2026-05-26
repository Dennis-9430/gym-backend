# Endpoints para gestión de ventas
# Relacionado con: models/sale.py, auth/router.py, database.py
"""Sales router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Optional
from datetime import datetime
from bson import ObjectId
from jose import JWTError, jwt
import asyncio
from pymongo import ReturnDocument
from app.models.sale import (
    SaleCreate, SaleUpdate, SaleResponse, SaleListResponse, SaleItem, PaymentMethod
)
from app.models.tenant import TenantResponse, SubscriptionPlan, SubscriptionStatus
from app.models.invoice import InvoiceStatus, PaymentMethodType
from app.models.sale import PaymentStatus
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.auth.cookie import get_token_from_request
from app.database import get_database, Collections
from app.utils.demo_protect import check_seed_protected
from app.config import settings


router = APIRouter(prefix="/api/sales", tags=["Sales"])


def serialize_sale(doc: dict) -> dict:
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
        if "createdBy" not in doc:
            doc["createdBy"] = "Sistema"
        if "cashAmount" not in doc:
            doc["cashAmount"] = 0.0
        if "transferAmount" not in doc:
            doc["transferAmount"] = 0.0
        client_fields = ["clientFirstName", "clientLastName", "clientDocument", 
                         "clientEmail", "clientPhone", "clientAddress",
                         "generateInvoice", "invoiceEmail"]
        for field in client_fields:
            if field not in doc:
                doc[field] = None
    return doc


async def get_tenant_from_header_sales(request: Request) -> TenantResponse:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id = payload.get("tenantId")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido"
            )
        
        # Obtener datos reales del tenant desde la base de datos
        db = get_database()
        tenant_doc = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
        
        plan_from_db = SubscriptionPlan.BASIC
        if tenant_doc and tenant_doc.get("plan"):
            plan_str = tenant_doc.get("plan")
            if plan_str in ["BASIC", "PREMIUM"]:
                plan_from_db = SubscriptionPlan(plan_str)
        
        return TenantResponse(
            id=tenant_id,
            tenantId=tenant_id,
            email="tenant@example.com",
            businessName=tenant_doc.get("businessName", "Mi Gimnasio") if tenant_doc else "Mi Gimnasio",
            businessPhone=tenant_doc.get("businessPhone", "") if tenant_doc else "",
            businessAddress=tenant_doc.get("businessAddress", "") if tenant_doc else "",
            businessRuc=tenant_doc.get("businessRuc", "") if tenant_doc else "",
            plan=plan_from_db if plan_from_db in ["BASIC", "PREMIUM"] else SubscriptionPlan.BASIC,
            subscriptionStatus=SubscriptionStatus.ACTIVE
        )
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )


@router.get("", response_model=SaleListResponse)
async def list_sales(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    client_id: Optional[int] = None,
    tenant: TenantResponse = Depends(get_tenant_from_header_sales)
):
    db = get_database()
    
    query = {"tenantId": tenant.tenantId}
    if start_date:
        query["createdAt"] = {"$gte": datetime.fromisoformat(start_date)}
    if end_date:
        if "createdAt" in query:
            query["createdAt"]["$lte"] = datetime.fromisoformat(end_date)
        else:
            query["createdAt"] = {"$lte": datetime.fromisoformat(end_date)}
    if client_id:
        query["clientId"] = client_id
    
    total = await db[Collections.SALES].count_documents(query)
    cursor = db[Collections.SALES].find(query).sort("createdAt", -1).skip(skip).limit(limit)
    sales = await cursor.to_list(length=limit)
    
    return {
        "sales": [serialize_sale(s) for s in sales],
        "total": total
    }


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: str,
    tenant: TenantResponse = Depends(get_tenant_from_header_sales)
):
    db = get_database()
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale ID"
        )
    
    # SEGURIDAD: filtrar por tenantId para evitar fuga entre negocios
    sale = await db[Collections.SALES].find_one({"_id": ObjectId(sale_id), "tenantId": tenant.tenantId})
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    return serialize_sale(sale)


@router.put("/{sale_id}", response_model=SaleResponse)
async def update_sale(
    sale_id: str,
    sale_data: SaleUpdate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_sales)
):
    """Actualiza el método de pago de una venta"""
    db = get_database()
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale ID"
        )
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant.tenantId, Collections.SALES, sale_id, "modificados")
    
    update_fields = sale_data.model_dump()
    
    # Si el método es CASH, ajustar montos
    if sale_data.paymentMethod == PaymentMethod.CASH:
        update_fields["cashAmount"] = update_fields.get("cashAmount", 0)
        update_fields["transferAmount"] = 0
    elif sale_data.paymentMethod == PaymentMethod.TRANSFER:
        update_fields["cashAmount"] = 0
        update_fields["transferAmount"] = update_fields.get("transferAmount", 0)
    
    result = await db[Collections.SALES].find_one_and_update(
        {"_id": ObjectId(sale_id), "tenantId": tenant.tenantId},
        {"$set": update_fields},
        return_document=ReturnDocument.AFTER
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    return serialize_sale(result)


from app.auth.router import get_current_user
from app.auth.schemas import UserResponse


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(
    sale_data: SaleCreate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_sales)
):
    db = get_database()
    
    sale_doc = sale_data.model_dump()
    sale_doc["tenantId"] = tenant.tenantId
    sale_doc["createdBy"] = current_user.username
    sale_doc["createdAt"] = datetime.utcnow()
    
    # Establecer paymentStatus automáticamente
    payment_method = sale_data.paymentMethod.value if sale_data.paymentMethod else "CASH"
    voucher = sale_doc.get("voucherCode")
    
    # Efectivo = verificado, Transferencia/Depósito sin voucher = pendiente
    if payment_method == "CASH" or payment_method == "MIXED":
        sale_doc["paymentStatus"] = "verified"
    elif voucher and voucher.strip():
        sale_doc["paymentStatus"] = "verified"
    else:
        sale_doc["paymentStatus"] = "pending"
    
    for item in sale_doc.get("items", []):
        if item.get("productId"):
            product = await db[Collections.PRODUCTS].find_one(
                {"_id": ObjectId(item["productId"]), "tenantId": tenant.tenantId}
            )
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Producto {item['productId']} no encontrado para este tenant"
                )
            
            current_stock = product.get("stock", 0)
            quantity = item.get("quantity", 1)
            if current_stock < quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente para producto {product.get('name', item['productId'])}. Disponible: {current_stock}"
                )
            
            new_stock = current_stock - quantity
            # SEGURIDAD: filtrar por tenantId al descontar stock
            await db[Collections.PRODUCTS].update_one(
                {"_id": ObjectId(item["productId"]), "tenantId": tenant.tenantId},
                {"$set": {"stock": new_stock}}
            )
    
    result = await db[Collections.SALES].insert_one(sale_doc)
    sale_doc["_id"] = result.inserted_id
    
    # Generar factura si el checkbox está marcado
    if sale_data.generateInvoice:
        await generate_invoice_from_sale(db, sale_doc, tenant.tenantId, sale_data.invoiceEmail)
    
    return serialize_sale(sale_doc)


async def generate_invoice_from_sale(db, sale_doc: dict, tenant_id: str, invoice_email: Optional[str] = None):
    """Genera una factura automáticamente a partir de una venta"""
    # Obtener datos del tenant
    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    
    # Generar número de factura
    counter = await db.counters.find_one_and_update(
        {"tenantId": tenant_id},
        {"$inc": {"invoiceCount": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    invoice_count = counter["invoiceCount"]
    invoice_number = f"FAC-{datetime.now().year}-{invoice_count:06d}"
    
    # Preparar datos del cliente - usar invoiceEmail proveído o del cliente o null
    # Si invoiceEmail viene null, guardar como null (no usar default)
    client_email = invoice_email if invoice_email else sale_doc.get("clientEmail") or sale_doc.get("client", {}).get("email")
    # Si no hay email y es consumidor final, guardar null
    if not client_email or client_email == "sinemail@default.com":
        client_email = None
    
    client_doc = {
        "documentNumber": sale_doc.get("clientDocument") or sale_doc.get("client", {}).get("documentNumber", "99999999"),
        "firstName": sale_doc.get("clientFirstName") or sale_doc.get("client", {}).get("firstName", "Consumidor"),
        "lastName": sale_doc.get("clientLastName") or sale_doc.get("client", {}).get("lastName", "Final"),
        "email": client_email,
    }
    
    # Preparar items de la factura y determinar taxRate desde el servicio
    invoice_items = []
    effective_tax_rate = 0
    for item in sale_doc.get("items", []):
        item_tax_rate = 0
        service_id = item.get("serviceId")
        if service_id:
            # SEGURIDAD: filtrar por tenantId al buscar servicio
            service = await db[Collections.SERVICES].find_one({"_id": ObjectId(service_id), "tenantId": tenant_id})
            if service:
                item_tax_rate = service.get("taxRate", 0)
        else:
            product_id = item.get("productId")
            if product_id:
                # SEGURIDAD: filtrar por tenantId al buscar producto
                product = await db[Collections.PRODUCTS].find_one({"_id": ObjectId(product_id), "tenantId": tenant_id})
                if product:
                    item_tax_rate = product.get("taxRate", 0)
        
        invoice_items.append({
            "name": item.get("productName", "Producto"),
            "quantity": item.get("quantity", 1),
            "unitPrice": item.get("unitPrice", 0),
            "unitDiscount": item.get("unitDiscount", 0),
            "subtotal": item.get("subtotal", 0),
            "serviceId": service_id,
            "taxRate": item_tax_rate,
        })
        if item_tax_rate > effective_tax_rate:
            effective_tax_rate = item_tax_rate
    
    # Si ningún item tiene taxRate, usar el del tenant como fallback
    if effective_tax_rate <= 0:
        effective_tax_rate = tenant.get("taxRate", 0) if tenant else 0
    
    # Calcular totales con IVA incluido (SRI Ecuador)
    # El subtotal de la venta ES el PVP (total que paga el cliente)
    total_items = sum(item.get("subtotal", 0) for item in invoice_items)
    discount_amount = total_items * sale_doc.get("discount", 0) / 100 if sale_doc.get("discount") else 0
    pvp = total_items - discount_amount
    
    if effective_tax_rate > 0:
        subtotal = round(pvp / (1 + effective_tax_rate / 100), 2)
        tax_amount = round(pvp - subtotal, 2)
        total = pvp
    else:
        subtotal = pvp
        tax_amount = 0
        total = pvp
    
    # Datos del negocio
    business_data = {
        "name": tenant.get("businessName", "Gimnasio") if tenant else "Gimnasio",
        "ruc": tenant.get("businessRuc", "") if tenant else "",
        "address": tenant.get("businessAddress", "") if tenant else "",
        "phone": tenant.get("businessPhone", "") if tenant else "",
        "email": tenant.get("email", "") if tenant else "",
    }
    
    # Método de pago — usar montos reales del sale_doc
    cash_amount = sale_doc.get("cashAmount", 0) or 0
    transfer_amount = sale_doc.get("transferAmount", 0) or 0
    paid = round(cash_amount + transfer_amount, 2)
    # Cambio: lo que sobra del efectivo después de cubrir el total menos la transferencia
    change = round(max(0, cash_amount - max(0, total - transfer_amount)), 2)
    
    payment_method = sale_doc.get("paymentMethod", "CASH")
    if payment_method == "CASH":
        payment_data = {
            "method": PaymentMethodType.CASH,
            "cashAmount": cash_amount,
            "transferAmount": 0,
            "paid": paid,
            "change": change,
        }
    elif payment_method == "TRANSFER":
        payment_data = {
            "method": PaymentMethodType.TRANSFER,
            "cashAmount": 0,
            "transferAmount": transfer_amount,
            "paid": paid,
            "change": 0,
        }
    else:
        payment_data = {
            "method": PaymentMethodType.MIXED,
            "cashAmount": cash_amount,
            "transferAmount": transfer_amount,
            "paid": paid,
            "change": change,
        }
    
    # Crear documento de factura
    invoice_doc = {
        "tenantId": tenant_id,
        "createdBy": sale_doc.get("createdBy", "Sistema"),
        "type": "PRODUCT",
        "invoiceNumber": invoice_number,
        "business": business_data,
        "client": client_doc,
        "items": invoice_items,
        "totals": {
            "subtotal": subtotal,
            "discountAmount": discount_amount,
            "taxAmount": tax_amount,
            "iceAmount": 0,
            "total": total,
        },
        "payment": payment_data,
        "status": InvoiceStatus.GENERATED.value,
        "createdAt": datetime.utcnow(),
    }
    
    await db[Collections.INVOICES].insert_one(invoice_doc)
    
    # Enviar email en background (sin esperar)
    if client_email and client_email != "sinemail@default.com":
        asyncio.create_task(send_invoice_email_async(db, invoice_doc, client_email))


async def send_invoice_email_async(db, invoice_doc: dict, email: str):
    """Envía email de factura en background vía Brevo"""
    try:
        from app.services.email import send_email

        inv = invoice_doc
        biz = inv.get("business", {})
        client = inv.get("client", {})
        totals = inv.get("totals", {})
        payment = inv.get("payment", {})

        created_at = inv.get("createdAt", datetime.utcnow())
        if hasattr(created_at, "strftime"):
            created_at_str = created_at.strftime("%d/%m/%Y %H:%M")
        else:
            created_at_str = str(created_at)

        payment_labels = {"CASH": "Efectivo", "TRANSFER": "Transferencia", "MIXED": "Mixto"}
        payment_method = payment_labels.get(payment.get("method", ""), payment.get("method", ""))

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
        <div style="border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 24px;">
            <h2 style="color: #1f2937; margin: 0 0 4px 0;">{biz.get("name", "")}</h2>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">RUC: {biz.get("ruc", "")}</p>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">
                {biz.get("address", "")} | Tel: {biz.get("phone", "")} | {biz.get("email", "")}
            </p>
        </div>

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

        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
            <thead>
                <tr style="background: #f3f4f6;">
                    <th style="padding: 8px 12px; text-align: left; font-size: 11px; color: #6b7280; text-transform: uppercase;">Código</th>
                    <th style="padding: 8px 12px; text-align: left; font-size: 11px; color: #6b7280; text-transform: uppercase;">Descripción</th>
                    <th style="padding: 8px 12px; text-align: center; font-size: 11px; color: #6b7280; text-transform: uppercase;">Cant.</th>
                    <th style="padding: 8px 12px; text-align: right; font-size: 11px; color: #6b7280; text-transform: uppercase;">Precio Unit.</th>
                    <th style="padding: 8px 12px; text-align: right; font-size: 11px; color: #6b7280; text-transform: uppercase;">Dto.</th>
                    <th style="padding: 8px 12px; text-align: right; font-size: 11px; color: #6b7280; text-transform: uppercase;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                {items_rows}
            </tbody>
        </table>

        <div style="border-top: 2px solid #e5e7eb; padding-top: 16px; margin-bottom: 24px;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">Subtotal:</td>
                    <td style="text-align: right; padding: 4px 0; font-size: 14px; color: #374151; width: 140px;">${totals.get("subtotal", 0):.2f}</td>
                </tr>
                <tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">Descuento:</td>
                    <td style="text-align: right; padding: 4px 0; font-size: 14px; color: #dc2626; width: 140px;">{totals.get("discountAmount", 0):.2f}</td>
                </tr>
                {"".join(f'''<tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">ICE:</td>
                    <td style="text-align: right; padding: 4px 0; font-size: 14px; color: #374151; width: 140px;">${{totals.get("iceAmount", 0):.2f}}</td>
                </tr>''' for _ in [1] if totals.get("iceAmount", 0) > 0)}
                <tr>
                    <td style="text-align: right; padding: 4px 12px; font-size: 14px; color: #4b5563;">IVA ({totals.get("taxAmount", 0) / totals.get("subtotal", 1) * 100:.0f}%):</td>
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

        <div style="background: #f9fafb; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
            <h4 style="color: #374151; margin: 0 0 8px 0; font-size: 14px;">Información de pago</h4>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Método: {payment_method}</p>
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Efectivo: ${payment.get("cashAmount", 0):.2f}</p>
            {"".join(f'<p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Transferencia: ${payment.get("transferAmount", 0):.2f}</p>' for _ in [1] if payment.get("transferAmount", 0) > 0)}
            <p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Pagado: <strong>${payment.get("paid", 0):.2f}</strong></p>
            {"".join(f'<p style="color: #6b7280; margin: 2px 0; font-size: 13px;">Cambio: ${payment.get("change", 0):.2f}</p>' for _ in [1] if payment.get("change", 0) > 0)}
        </div>

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

        success = await send_email(
            to=email,
            subject=subject,
            html=html,
            text=text,
        )

        if success:
            await db[Collections.INVOICES].update_one(
                {"invoiceNumber": inv.get("invoiceNumber"), "tenantId": inv.get("tenantId")},
                {"$set": {
                    "status": InvoiceStatus.SENT.value,
                    "emailDelivery": {"sent": True, "sentAt": datetime.utcnow(), "recipient": email}
                }}
            )
        else:
            await db[Collections.INVOICES].update_one(
                {"invoiceNumber": inv.get("invoiceNumber"), "tenantId": inv.get("tenantId")},
                {"$set": {"status": InvoiceStatus.FAILED.value}}
            )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Error enviando factura %s a %s: %s", invoice_doc.get("invoiceNumber", ""), email, e)
        await db[Collections.INVOICES].update_one(
            {"invoiceNumber": invoice_doc.get("invoiceNumber"), "tenantId": invoice_doc.get("tenantId")},
            {"$set": {"status": InvoiceStatus.FAILED.value}}
        )


@router.delete("/{sale_id}")
async def delete_sale(
    sale_id: str,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_sales)
):
    if current_user.role.value not in ["GERENTE"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el gerente puede eliminar ventas"
        )
    
    db = get_database()
    tenant_id = tenant.tenantId
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale ID"
        )
    
    # Proteger seed data en cuentas demo
    await check_seed_protected(db, tenant.tenantId, Collections.SALES, sale_id, "eliminados")
    
    result = await db[Collections.SALES].delete_one({"_id": ObjectId(sale_id), "tenantId": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    return {"message": "Sale deleted successfully"}


@router.put("/{sale_id}/voucher")
async def update_voucher(
    sale_id: str,
    voucher_data: dict,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_sales)
):
    """Actualiza voucher y/o imagen del comprobante - Todos pueden usar"""
    db = get_database()
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(status_code=400, detail="Invalid sale ID")
    
    update_data = {}
    if "voucherCode" in voucher_data:
        update_data["voucherCode"] = voucher_data["voucherCode"]
    if "voucherImage" in voucher_data:
        update_data["voucherImage"] = voucher_data["voucherImage"]
    
    # Si se proporciona voucher, cambia estado a verificado
    if voucher_data.get("voucherCode"):
        update_data["paymentStatus"] = "verified"
    
    if update_data:
        await db[Collections.SALES].update_one(
            {"_id": ObjectId(sale_id), "tenantId": tenant.tenantId},
            {"$set": update_data}
        )
    
    return {"message": "Voucher actualizado"}


@router.put("/{sale_id}/verify")
async def verify_payment(
    sale_id: str,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_sales)
):
    """Marca pago como verificado - Solo ADMIN"""
    if current_user.role.value not in ["ADMIN", "GERENTE"]:
        raise HTTPException(
            status_code=403,
            detail="Solo administradores o gerentes pueden verificar pagos"
        )
    
    db = get_database()
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(status_code=400, detail="Invalid sale ID")
    
    await db[Collections.SALES].update_one(
        {"_id": ObjectId(sale_id), "tenantId": tenant.tenantId},
        {"$set": {"paymentStatus": "verified"}}
    )
    
    return {"message": "Pago verificado"}
