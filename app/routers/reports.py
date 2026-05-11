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


# NOTA: get_tenant_from_header_* está duplicado en 7 routers (reports, sales, products,
# clients, tenants, invoices, employees). Técnicamente debería unificarse en una
# dependencia común tipo get_current_tenant() en app/auth/deps.py.
# Pendiente para refactor post-seguridad.
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
            email="tenant@example.com",
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
    
    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": None,
                "totalSales": {"$sum": 1},
                "totalRevenue": {"$sum": "$total"},
                "cashRevenue": {
                    "$sum": {"$cond": [{"$eq": ["$paymentMethod", "CASH"]}, "$total", 0]}
                },
                "cardRevenue": {
                    "$sum": {"$cond": [{"$eq": ["$paymentMethod", "CARD"]}, "$total", 0]}
                },
                "transferRevenue": {
                    "$sum": {"$cond": [{"$eq": ["$paymentMethod", "TRANSFER"]}, "$total", 0]}
                },
            }
        },
    ]
    cursor = db[Collections.SALES].aggregate(pipeline)
    result = await cursor.to_list(length=1)
    
    if not result:
        summary = {"totalSales": 0, "totalRevenue": 0, "cashRevenue": 0, "cardRevenue": 0, "transferRevenue": 0}
    else:
        r = result[0]
        summary = {
            "totalSales": r["totalSales"],
            "totalRevenue": r["totalRevenue"],
            "cashRevenue": r["cashRevenue"],
            "cardRevenue": r["cardRevenue"],
            "transferRevenue": r["transferRevenue"],
        }
    
    return {
        "period": {
            "start": start_date,
            "end": end_date
        },
        "summary": summary
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
    
    pipeline = [
        {
            "$match": {
                "tenantId": tenant.tenantId,
                "createdAt": {"$gte": start, "$lt": end}
            }
        },
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
                "sales": {"$sum": 1},
                "revenue": {"$sum": "$total"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    cursor = db[Collections.SALES].aggregate(pipeline)
    grouped = {}
    async for row in cursor:
        grouped[row["_id"]] = {"sales": row["sales"], "revenue": row["revenue"]}
    
    # Rellenar días sin ventas con cero
    daily_data = []
    current = start
    while current < end:
        date_str = current.strftime("%Y-%m-%d")
        entry = grouped.get(date_str, {"sales": 0, "revenue": 0})
        daily_data.append({"date": date_str, "sales": entry["sales"], "revenue": entry["revenue"]})
        current += timedelta(days=1)
    
    return {
        "year": year,
        "month": month,
        "data": daily_data
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
    
    pipeline = [
        {
            "$match": {
                "tenantId": tenant.tenantId,
                "checkIn": {"$gte": start_date}
            }
        },
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$checkIn"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    cursor = db[Collections.ATTENDANCE].aggregate(pipeline)
    grouped = {}
    total = 0
    async for row in cursor:
        grouped[row["_id"]] = row["count"]
        total += row["count"]
    
    # Rellenar días sin registros con cero
    daily_attendance = []
    for i in range(days - 1, -1, -1):
        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_attendance.append({"date": date, "count": grouped.get(date, 0)})
    
    return {
        "period": f"Last {days} days",
        "total": total,
        "daily": daily_attendance
    }
