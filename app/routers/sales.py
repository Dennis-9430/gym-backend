# Endpoints para gestión de ventas
# Relacionado con: models/sale.py, auth/router.py, database.py
"""Sales router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from typing import Optional
from datetime import datetime
from bson import ObjectId
from jose import JWTError, jwt
import asyncio
from app.models.sale import (
    SaleCreate, SaleResponse, SaleListResponse, SaleItem, PaymentMethod
)
from app.models.tenant import TenantResponse, SubscriptionPlan, SubscriptionStatus
from app.models.invoice import InvoiceStatus, PaymentMethodType
from app.models.sale import PaymentStatus
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections
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


async def get_tenant_from_header_sales(authorization: str = Header(None)) -> TenantResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado"
        )
    
    token = authorization.replace("Bearer ", "")
    
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
            email=payload.get("sub", "") or "tenant@example.com",
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
    
    sale = await db[Collections.SALES].find_one({"_id": ObjectId(sale_id)})
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )
    
    return serialize_sale(sale)


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
            await db[Collections.PRODUCTS].update_one(
                {"_id": ObjectId(item["productId"])},
                {"$set": {"stock": new_stock}}
            )
    
    result = await db[Collections.SALES].insert_one(sale_doc)
    
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
        upsert=True
    )
    invoice_count = counter.get("invoiceCount", 1) if counter else 1
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
    
    # Preparar items de la factura
    invoice_items = []
    for item in sale_doc.get("items", []):
        invoice_items.append({
            "name": item.get("productName", "Producto"),
            "quantity": item.get("quantity", 1),
            "unitPrice": item.get("unitPrice", 0),
            "unitDiscount": item.get("unitDiscount", 0),
            "subtotal": item.get("subtotal", 0),
        })
    
    # Calcular totales
    subtotal = sum(item.get("subtotal", 0) for item in invoice_items)
    discount_amount = subtotal * sale_doc.get("discount", 0) / 100 if sale_doc.get("discount") else 0
    taxable_subtotal = subtotal - discount_amount
    tax_rate = tenant.get("taxRate", 12) if tenant else 12
    tax_amount = taxable_subtotal * tax_rate / 100
    total = taxable_subtotal + tax_amount
    
    # Datos del negocio
    business_data = {
        "name": tenant.get("businessName", "Gimnasio") if tenant else "Gimnasio",
        "ruc": tenant.get("businessRuc", "") if tenant else "",
        "address": tenant.get("businessAddress", "") if tenant else "",
        "phone": tenant.get("businessPhone", "") if tenant else "",
        "email": tenant.get("email", "") if tenant else "",
    }
    
    # Método de pago
    payment_method = sale_doc.get("paymentMethod", "CASH")
    if payment_method == "CASH":
        payment_data = {
            "method": PaymentMethodType.CASH,
            "cashAmount": total,
            "transferAmount": 0,
            "paid": total,
            "change": 0,
        }
    elif payment_method == "TRANSFER":
        payment_data = {
            "method": PaymentMethodType.TRANSFER,
            "cashAmount": 0,
            "transferAmount": total,
            "paid": total,
            "change": 0,
        }
    else:
        payment_data = {
            "method": PaymentMethodType.MIXED,
            "cashAmount": sale_doc.get("cashAmount", 0),
            "transferAmount": sale_doc.get("transferAmount", 0),
            "paid": total,
            "change": 0,
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
    """Envía email de factura en background"""
    try:
        # Aquí iría la lógica de envío de email
        # Por ahora solo actualizamos el estado
        await db[Collections.INVOICES].update_one(
            {"invoiceNumber": invoice_doc.get("invoiceNumber"), "tenantId": invoice_doc.get("tenantId")},
            {"$set": {"status": InvoiceStatus.SENT.value, "emailDelivery": {"sent": True, "sentAt": datetime.utcnow()}}}
        )
    except Exception as e:
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
    if current_user.role.value not in ["ADMIN", "GERENTE"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores o gerentes pueden eliminar ventas"
        )
    
    db = get_database()
    tenant_id = tenant.tenantId
    
    if not ObjectId.is_valid(sale_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale ID"
        )
    
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