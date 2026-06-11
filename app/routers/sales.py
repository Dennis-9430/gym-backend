# Endpoints para gestión de ventas
# Relacionado con: models/sale.py, auth/router.py, database.py
"""Sales router — thin controllers delegating to SalesService"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from typing import Optional

from app.models.sale import (
    SaleCreate, SaleUpdate, SaleResponse, SaleListResponse, PaymentMethod
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.api.dependencies import get_tenant_from_request
from app.database import get_database
from app.services.sales_service import SalesService


router = APIRouter(prefix="/api/sales", tags=["Sales"])


def serialize_sale(doc: dict) -> dict:
    """Public helper — kept for backward compat (delegates to service)."""
    return SalesService._serialize_sale(None, doc) if doc else doc


@router.get("", response_model=SaleListResponse)
async def list_sales(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    client_id: Optional[int] = None,
    tenant: dict = Depends(get_tenant_from_request),
):
    db = get_database()
    service = SalesService(db)
    return await service.list_sales(
        tenant_id=tenant["tenantId"],
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        client_id=client_id,
    )


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: str,
    tenant: dict = Depends(get_tenant_from_request),
):
    db = get_database()
    service = SalesService(db)
    return await service.get_sale(sale_id, tenant["tenantId"])


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(
    sale_data: SaleCreate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: dict = Depends(get_tenant_from_request),
):
    db = get_database()
    service = SalesService(db)
    # Convert Pydantic model to dict for service
    sale_dict = sale_data.model_dump()
    return await service.create_sale(
        sale_data=sale_dict,
        tenant_id=tenant["tenantId"],
        created_by=current_user.username,
    )


@router.put("/{sale_id}", response_model=SaleResponse)
async def update_sale(
    sale_id: str,
    sale_data: SaleUpdate,
    current_user: UserResponse = Depends(get_current_user),
    tenant: dict = Depends(get_tenant_from_request),
):
    """Actualiza el método de pago de una venta"""
    db = get_database()
    service = SalesService(db)
    return await service.update_sale(
        sale_id=sale_id,
        sale_data=sale_data.model_dump(),
        tenant_id=tenant["tenantId"],
    )


@router.delete("/{sale_id}")
async def delete_sale(
    sale_id: str,
    current_user: UserResponse = Depends(get_current_user),
    tenant: dict = Depends(get_tenant_from_request),
):
    if current_user.role.value not in ["GERENTE"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el gerente puede eliminar ventas",
        )

    db = get_database()
    service = SalesService(db)
    await service.delete_sale(sale_id, tenant["tenantId"])
    return Response(status_code=204)


@router.put("/{sale_id}/voucher")
async def update_voucher(
    sale_id: str,
    voucher_data: dict,
    current_user: UserResponse = Depends(get_current_user),
    tenant: dict = Depends(get_tenant_from_request),
):
    """Actualiza voucher y/o imagen del comprobante - Todos pueden usar"""
    db = get_database()
    service = SalesService(db)
    return await service.update_voucher(sale_id, voucher_data, tenant["tenantId"])


@router.put("/{sale_id}/verify")
async def verify_payment(
    sale_id: str,
    current_user: UserResponse = Depends(get_current_user),
    tenant: dict = Depends(get_tenant_from_request),
):
    """Marca pago como verificado - Solo ADMIN"""
    if current_user.role.value not in ["ADMIN", "GERENTE"]:
        raise HTTPException(
            status_code=403,
            detail="Solo administradores o gerentes pueden verificar pagos",
        )

    db = get_database()
    service = SalesService(db)
    return await service.verify_payment(sale_id, tenant["tenantId"])
