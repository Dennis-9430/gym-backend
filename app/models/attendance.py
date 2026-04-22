# Esquemas Pydantic para asistencia
# Relacionado con: routers/attendance.py, database.py
"""Attendance Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AttendanceBase(BaseModel):
    # Datos base de asistencia
    # Relacionado con: routers/attendance.py
    clientId: int
    clientName: str


class AttendanceCheckIn(AttendanceBase):
    # Datos para registrar entrada
    # Relacionado con: routers/attendance.py (check_in)
    pass


class AttendanceCheckOut(BaseModel):
    # Datos para registrar salida
    # Relacionado con: routers/attendance.py (check_out)
    checkOut: datetime


class AttendanceResponse(AttendanceBase):
    # Respuesta con todos los datos de asistencia
    # Relacionado con: routers/attendance.py (get_attendance)
    id: str = Field(..., alias="_id")
    checkIn: datetime
    checkOut: Optional[datetime] = None
    date: str

    class Config:
        populate_by_name = True


class AttendanceListResponse(BaseModel):
    # Lista de asistencia con paginación
    # Relacionado con: routers/attendance.py (list_attendance)
    records: list[AttendanceResponse]
    total: int
