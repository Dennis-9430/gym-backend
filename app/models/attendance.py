"""Attendance Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AttendanceBase(BaseModel):
    clientId: int
    clientName: str


class AttendanceCheckIn(AttendanceBase):
    pass


class AttendanceCheckOut(BaseModel):
    checkOut: datetime


class AttendanceResponse(AttendanceBase):
    id: str = Field(..., alias="_id")
    checkIn: datetime
    checkOut: Optional[datetime] = None
    date: str

    class Config:
        populate_by_name = True


class AttendanceListResponse(BaseModel):
    records: list[AttendanceResponse]
    total: int
