# Endpoints para gestión de asistencia
# Relacionado con: models/attendance.py, auth/router.py, database.py
"""Attendance router"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from datetime import datetime
from bson import ObjectId
from app.models.attendance import (
    AttendanceCheckIn, AttendanceCheckOut, 
    AttendanceResponse, AttendanceListResponse
)
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.database import get_database, Collections


router = APIRouter(prefix="/api/attendance", tags=["Attendance"])


def serialize_attendance(doc: dict) -> dict:
    if doc:
        doc["id"] = str(doc.get("_id", ""))
        doc.pop("_id", None)
    return doc


@router.get("", response_model=AttendanceListResponse)
async def list_attendance(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    client_id: Optional[int] = None,
    date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    # SEGURIDAD: filtrar por tenantId del usuario autenticado
    query = {"tenantId": current_user.tenantId}
    if client_id:
        query["clientId"] = client_id
    if date:
        query["date"] = date
    
    total = await db[Collections.ATTENDANCE].count_documents(query)
    cursor = db[Collections.ATTENDANCE].find(query).sort("checkIn", -1).skip(skip).limit(limit)
    records = await cursor.to_list(length=limit)
    
    return {
        "records": [serialize_attendance(r) for r in records],
        "total": total
    }


@router.post("/checkin", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
async def check_in(
    data: AttendanceCheckIn,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # SEGURIDAD: verificar que el cliente pertenezca al mismo tenant
    existing = await db[Collections.ATTENDANCE].find_one({
        "clientId": data.clientId,
        "date": today,
        "tenantId": current_user.tenantId,
        "checkOut": None
    })
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client already checked in today"
        )
    
    now = datetime.utcnow()
    record = {
        "clientId": data.clientId,
        "clientName": data.clientName,
        "checkIn": now,
        "checkOut": None,
        "date": today,
        "tenantId": current_user.tenantId
    }
    
    result = await db[Collections.ATTENDANCE].insert_one(record)
    record["_id"] = str(result.inserted_id)
    
    return record


@router.put("/{attendance_id}/checkout", response_model=AttendanceResponse)
async def check_out(
    attendance_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    
    if not ObjectId.is_valid(attendance_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid attendance ID"
        )
    
    # SEGURIDAD: filtrar por tenantId
    record = await db[Collections.ATTENDANCE].find_one({"_id": ObjectId(attendance_id), "tenantId": current_user.tenantId})
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found"
        )
    
    if record.get("checkOut"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already checked out"
        )
    
    now = datetime.utcnow()
    await db[Collections.ATTENDANCE].update_one(
        {"_id": ObjectId(attendance_id), "tenantId": current_user.tenantId},
        {"$set": {"checkOut": now}}
    )
    
    # SEGURIDAD: read-back también filtra por tenantId
    updated = await db[Collections.ATTENDANCE].find_one({"_id": ObjectId(attendance_id), "tenantId": current_user.tenantId})
    return serialize_attendance(updated)


@router.get("/today")
async def get_today_attendance(
    current_user: UserResponse = Depends(get_current_user)
):
    db = get_database()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # SEGURIDAD: filtrar por tenantId
    total = await db[Collections.ATTENDANCE].count_documents({"date": today, "tenantId": current_user.tenantId})
    checked_in = await db[Collections.ATTENDANCE].count_documents({
        "date": today,
        "tenantId": current_user.tenantId,
        "checkOut": None
    })
    
    return {
        "date": today,
        "total": total,
        "currentlyIn": checked_in
    }
