# Endpoints para reportes financieros
# Relacionado con: database.py, routers/sales.py, models/sale.py
"""Financial reports router"""
from fastapi import APIRouter, Depends, Query, Header, HTTPException, status
from typing import Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.models.tenant import TenantResponse, SubscriptionPlan, SubscriptionStatus
from app.database import get_database, Collections
from app.config import settings


router = APIRouter(prefix="/api/reports", tags=["Reports"])


async def get_tenant_from_header_reports(authorization: str = Header(None)) -> TenantResponse:
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
        
        status_from_db = SubscriptionStatus.ACTIVE
        if tenant_doc and tenant_doc.get("subscriptionStatus"):
            status_str = tenant_doc.get("subscriptionStatus")
            if status_str in ["ACTIVE", "EXPIRED", "PENDING", "CANCELLED"]:
                status_from_db = SubscriptionStatus(status_str)
        
        return TenantResponse(
            id=tenant_id,
            tenantId=tenant_id,
            email=payload.get("sub", "") or "tenant@example.com",
            businessName=tenant_doc.get("businessName", "Mi Gimnasio") if tenant_doc else "Mi Gimnasio",
            businessPhone=tenant_doc.get("businessPhone") if tenant_doc else None,
            businessAddress=tenant_doc.get("businessAddress") if tenant_doc else None,
            businessRuc=tenant_doc.get("businessRuc") if tenant_doc else None,
            plan=plan_from_db,
            subscriptionStatus=status_from_db,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )


@router.get("/financial/summary")
async def get_financial_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_reports)
):
    db = get_database()
    
    date_filter = {}
    if start_date:
        date_filter["$gte"] = datetime.fromisoformat(start_date)
    if end_date:
        date_filter["$lte"] = datetime.fromisoformat(end_date)
    
    query = {"tenantId": tenant.tenantId}
    if date_filter:
        query["createdAt"] = date_filter
    
    sales = await db[Collections.SALES].find(query).to_list(length=10000)
    
    total_sales = len(sales)
    total_revenue = sum(s.get("total", 0) for s in sales)
    
    cash_sales = [s for s in sales if s.get("paymentMethod") == "CASH"]
    card_sales = [s for s in sales if s.get("paymentMethod") == "CARD"]
    transfer_sales = [s for s in sales if s.get("paymentMethod") == "TRANSFER"]
    
    return {
        "period": {
            "start": start_date,
            "end": end_date
        },
        "summary": {
            "totalSales": total_sales,
            "totalRevenue": total_revenue,
            "cashRevenue": sum(s.get("total", 0) for s in cash_sales),
            "cardRevenue": sum(s.get("total", 0) for s in card_sales),
            "transferRevenue": sum(s.get("total", 0) for s in transfer_sales)
        }
    }


@router.get("/financial/daily")
async def get_daily_report(
    year: int,
    month: int,
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_reports)
):
    db = get_database()
    
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    
    sales = await db[Collections.SALES].find({
        "tenantId": tenant.tenantId,
        "createdAt": {"$gte": start, "$lt": end}
    }).to_list(length=10000)
    
    daily_data = {}
    current = start
    while current < end:
        date_str = current.strftime("%Y-%m-%d")
        daily_data[date_str] = {"sales": 0, "revenue": 0}
        current += timedelta(days=1)
    
    for sale in sales:
        date_str = sale.get("createdAt", datetime.utcnow()).strftime("%Y-%m-%d")
        if date_str in daily_data:
            daily_data[date_str]["sales"] += 1
            daily_data[date_str]["revenue"] += sale.get("total", 0)
    
    return {
        "year": year,
        "month": month,
        "data": [
            {"date": date, "sales": data["sales"], "revenue": data["revenue"]}
            for date, data in daily_data.items()
        ]
    }


@router.get("/clients/summary")
async def get_clients_summary(
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_reports)
):
    db = get_database()
    
    total_clients = await db[Collections.CLIENTS].count_documents({"tenantId": tenant.tenantId})
    
    active = await db[Collections.CLIENTS].count_documents({"tenantId": tenant.tenantId, "membershipStatus": "ACTIVE"})
    expired = await db[Collections.CLIENTS].count_documents({"tenantId": tenant.tenantId, "membershipStatus": "EXPIRED"})
    none = await db[Collections.CLIENTS].count_documents({"tenantId": tenant.tenantId, "membershipStatus": "NONE"})
    
    return {
        "total": total_clients,
        "active": active,
        "expired": expired,
        "none": none
    }


@router.get("/attendance/summary")
async def get_attendance_summary(
    days: int = Query(7, ge=1, le=30),
    current_user: UserResponse = Depends(get_current_user),
    tenant: TenantResponse = Depends(get_tenant_from_header_reports)
):
    db = get_database()
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    records = await db[Collections.ATTENDANCE].find({
        "tenantId": tenant.tenantId,
        "checkIn": {"$gte": start_date}
    }).to_list(length=10000)
    
    daily_attendance = {}
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_attendance[date] = 0
    
    for record in records:
        date_str = record.get("checkIn", datetime.utcnow()).strftime("%Y-%m-%d")
        if date_str in daily_attendance:
            daily_attendance[date_str] += 1
    
    return {
        "period": f"Last {days} days",
        "total": len(records),
        "daily": [
            {"date": date, "count": count}
            for date, count in daily_attendance.items()
        ]
    }
