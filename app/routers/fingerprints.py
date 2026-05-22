# Endpoints para gestión de huellas biométricas
# Relacionado con: models/employee.py, models/client.py, database.py
"""Fingerprint management router — register/delete/status check"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from bson import ObjectId
from app.database import get_database, Collections
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse, UserRole
from app.models.employee import EmployeeRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fingerprints", tags=["Fingerprints"])


class FingerprintRegisterRequest(BaseModel):
    entityType: str  # "client" | "employee"
    entityId: str


class FingerprintStatusResponse(BaseModel):
    registered: bool
    entityType: str
    entityId: str


async def _check_biometric_enabled(tenant_id: str) -> bool:
    """Verifica que el tenant tenga biometricEnabled = True."""
    db = get_database()
    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    return tenant.get("biometricEnabled", False) if tenant else False


async def _can_manage_fingerprint(
    current_role: str,
    current_is_owner: bool,
    target_role: str | None,
) -> bool:
    """Verifica si el usuario actual puede gestionar huella del target.
    
    Jerarquía:
      GERENTE (owner) → ADMIN, RECEPCIONISTA, CLIENTES
      ADMIN            → RECEPCIONISTA, CLIENTES
      RECEPCIONISTA    → CLIENTES (solamente)
    """
    # Para clientes, cualquier rol puede gestionar
    if target_role is None:
        return current_role in ["GERENTE", "ADMIN", "RECEPCIONISTA"]
    
    # GERENTE puede todo
    if current_is_owner or current_role == "GERENTE":
        return target_role in ["ADMIN", "RECEPCIONISTA"]
    
    # ADMIN puede gestionar RECEPCIONISTA
    if current_role == "ADMIN":
        return target_role == "RECEPCIONISTA"
    
    # RECEPCIONISTA no gestiona empleados
    return False


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_fingerprint(
    data: FingerprintRegisterRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Registrar huella biométrica para un cliente o empleado."""
    if current_user.tenantId is None:
        raise HTTPException(status_code=403, detail="Acción no permitida para SUPER_ADMIN")
    
    # Verificar que el tenant tenga biométrica habilitada
    if not await _check_biometric_enabled(current_user.tenantId):
        raise HTTPException(status_code=400, detail="Biometría no habilitada para este negocio")
    
    db = get_database()
    
    if data.entityType == "client":
        # Buscar cliente
        client = await db[Collections.CLIENTS].find_one({
            "_id": ObjectId(data.entityId) if ObjectId.is_valid(data.entityId) else data.entityId,
            "tenantId": current_user.tenantId,
        })
        if not client:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
        # Cualquier rol puede registrar huella de cliente
        # (authorizado por _can_manage_fingerprint con target_role=None)
        if not await _can_manage_fingerprint(current_user.role, current_user.isOwner or False, None):
            raise HTTPException(status_code=403, detail="No tienes permiso para registrar huellas")
        
        # Actualizar cliente
        await db[Collections.CLIENTS].update_one(
            {"_id": client["_id"]},
            {"$set": {"fingerPrint": True, "updatedAt": __import__('datetime').datetime.utcnow()}}
        )
        
    elif data.entityType == "employee":
        # Buscar empleado
        try:
            oid = ObjectId(data.entityId)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de empleado inválido")
        
        employee = await db[Collections.EMPLOYEES].find_one({
            "_id": oid,
            "tenantId": current_user.tenantId,
        })
        if not employee:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        
        # Verificar permisos según jerarquía
        target_role = employee.get("role", "")
        if not await _can_manage_fingerprint(current_user.role, current_user.isOwner or False, target_role):
            raise HTTPException(status_code=403, detail="No tienes permiso para registrar huella de este empleado")
        
        # No permitir registrar huella del owner por otro
        if employee.get("isOwner", False) and not current_user.isOwner:
            raise HTTPException(status_code=403, detail="No puedes registrar la huella del propietario")
        
        await db[Collections.EMPLOYEES].update_one(
            {"_id": oid},
            {"$set": {"fingerPrint": True, "updatedAt": __import__('datetime').datetime.utcnow()}}
        )
    else:
        raise HTTPException(status_code=400, detail="entityType debe ser 'client' o 'employee'")
    
    return {"message": "Huella registrada correctamente"}


@router.delete("/{entity_type}/{entity_id}", status_code=status.HTTP_200_OK)
async def delete_fingerprint(
    entity_type: str,
    entity_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """Eliminar huella biométrica de un cliente o empleado."""
    if current_user.tenantId is None:
        raise HTTPException(status_code=403, detail="Acción no permitida para SUPER_ADMIN")
    
    if not await _check_biometric_enabled(current_user.tenantId):
        raise HTTPException(status_code=400, detail="Biometría no habilitada para este negocio")
    
    db = get_database()
    
    if entity_type == "client":
        client = await db[Collections.CLIENTS].find_one({
            "_id": ObjectId(entity_id) if ObjectId.is_valid(entity_id) else entity_id,
            "tenantId": current_user.tenantId,
        })
        if not client:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
        if not await _can_manage_fingerprint(current_user.role, current_user.isOwner or False, None):
            raise HTTPException(status_code=403, detail="No tienes permiso para eliminar huellas")
        
        await db[Collections.CLIENTS].update_one(
            {"_id": client["_id"]},
            {"$set": {"fingerPrint": False, "updatedAt": __import__('datetime').datetime.utcnow()}}
        )
        
    elif entity_type == "employee":
        try:
            oid = ObjectId(entity_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de empleado inválido")
        
        employee = await db[Collections.EMPLOYEES].find_one({
            "_id": oid,
            "tenantId": current_user.tenantId,
        })
        if not employee:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        
        target_role = employee.get("role", "")
        if not await _can_manage_fingerprint(current_user.role, current_user.isOwner or False, target_role):
            raise HTTPException(status_code=403, detail="No tienes permiso para eliminar huella de este empleado")
        
        if employee.get("isOwner", False) and not current_user.isOwner:
            raise HTTPException(status_code=403, detail="No puedes eliminar la huella del propietario")
        
        await db[Collections.EMPLOYEES].update_one(
            {"_id": oid},
            {"$set": {"fingerPrint": False, "updatedAt": __import__('datetime').datetime.utcnow()}}
        )
    else:
        raise HTTPException(status_code=400, detail="entityType debe ser 'client' o 'employee'")
    
    return {"message": "Huella eliminada correctamente"}


@router.get("/status/{entity_type}/{entity_id}", response_model=FingerprintStatusResponse)
async def get_fingerprint_status(
    entity_type: str,
    entity_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """Consultar si un cliente o empleado tiene huella registrada."""
    if current_user.tenantId is None:
        raise HTTPException(status_code=403, detail="Acción no permitida para SUPER_ADMIN")
    
    db = get_database()
    
    if entity_type == "client":
        client = await db[Collections.CLIENTS].find_one({
            "_id": ObjectId(entity_id) if ObjectId.is_valid(entity_id) else entity_id,
            "tenantId": current_user.tenantId,
        })
        if not client:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        return FingerprintStatusResponse(
            registered=client.get("fingerPrint", False),
            entityType=entity_type,
            entityId=entity_id,
        )
    
    elif entity_type == "employee":
        try:
            oid = ObjectId(entity_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de empleado inválido")
        
        employee = await db[Collections.EMPLOYEES].find_one({
            "_id": oid,
            "tenantId": current_user.tenantId,
        })
        if not employee:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        return FingerprintStatusResponse(
            registered=employee.get("fingerPrint", False),
            entityType=entity_type,
            entityId=entity_id,
        )
    
    raise HTTPException(status_code=400, detail="entityType debe ser 'client' o 'employee'")


@router.get("/biometric-config")
async def get_biometric_config(
    current_user: UserResponse = Depends(get_current_user),
):
    """Devuelve si la biometría está habilitada para el tenant actual."""
    if current_user.tenantId is None:
        return {"biometricEnabled": False}
    
    db = get_database()
    tenant = await db[Collections.TENANTS].find_one({"tenantId": current_user.tenantId})
    return {"biometricEnabled": tenant.get("biometricEnabled", False) if tenant else False}
