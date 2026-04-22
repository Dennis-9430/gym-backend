# Endpoints para reportes financieros
# Relacionado con: database.py, routers/sales.py, models/sale.py
"""Financial reports router"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timedelta
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections


router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/financial/summary")
async def get_financial_summary(
    # Resume financiero por periodo (ventas, ingresos por metodo de pago)
    # Relacionado con: database.py (Collections.SALES), models/sale.py
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    date_filter = {}
    if start_date:
        date_filter["$gte"] = datetime.fromisoformat(start_date)
    if end_date:
        date_filter["$lte"] = datetime.fromisoformat(end_date)
    
    query = {}
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
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    
    sales = await db[Collections.SALES].find({
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
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    total_clients = await db[Collections.CLIENTS].count_documents({})
    
    active = await db[Collections.CLIENTS].count_documents({"membershipStatus": "ACTIVE"})
    expired = await db[Collections.CLIENTS].count_documents({"membershipStatus": "EXPIRED"})
    none = await db[Collections.CLIENTS].count_documents({"membershipStatus": "NONE"})
    
    return {
        "total": total_clients,
        "active": active,
        "expired": expired,
        "none": none
    }


@router.get("/attendance/summary")
async def get_attendance_summary(
    days: int = Query(7, ge=1, le=30),
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    records = await db[Collections.ATTENDANCE].find({
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
