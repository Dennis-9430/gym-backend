# Router para Notificaciones WhatsApp
# SEGURIDAD: Todos los endpoints requieren autenticación y filtran por tenantId
"""Notifications API router"""
from fastapi import APIRouter, HTTPException, Depends
from app.models.notification import (
    NotificationConfigCreate,
    NotificationConfigUpdate,
    NotificationConfigResponse,
    NotificationLogResponse,
    NotificationType,
)
from app.database import get_database
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.auth.schemas import UserRole
from datetime import datetime

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

COLLECTION_CONFIG = "notification_configs"
COLLECTION_LOGS = "notification_logs"


# ============ CONFIG ENDPOINTS ============

def _serialize_config(doc: dict) -> dict:
    """Renombra _id a id para la respuesta"""
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("/configs", response_model=list[NotificationConfigResponse])
async def list_configs(current_user: UserResponse = Depends(get_current_user)):
    """Listar configuraciones del tenant - requiere auth"""
    db = get_database()
    # SEGURIDAD: filtrar por tenantId del usuario autenticado
    configs = await db[COLLECTION_CONFIG].find({"tenantId": current_user.tenantId}).to_list(100)
    return [_serialize_config(c) for c in configs]


@router.get("/configs/{config_type}", response_model=NotificationConfigResponse)
async def get_config(
    config_type: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """Obtener configuración por tipo - requiere auth"""
    db = get_database()
    # SEGURIDAD: filtrar por tenantId
    config = await db[COLLECTION_CONFIG].find_one({"type": config_type, "tenantId": current_user.tenantId})
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return _serialize_config(config)


@router.post("/configs")
async def create_or_update_config(
    config: NotificationConfigCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    """Crear o actualizar configuración del tenant - requiere auth"""
    db = get_database()
    config_dict = config.model_dump()
    config_dict["tenantId"] = current_user.tenantId
    config_dict["updatedAt"] = datetime.utcnow()
    
    # SEGURIDAD: buscar por tenantId + type
    existing = await db[COLLECTION_CONFIG].find_one({"type": config.type, "tenantId": current_user.tenantId})
    
    if existing:
        await db[COLLECTION_CONFIG].update_one(
            {"_id": existing["_id"]},
            {"$set": config_dict}
        )
    else:
        config_dict["createdAt"] = datetime.utcnow()
        config_dict["sentToday"] = False
        await db[COLLECTION_CONFIG].insert_one(config_dict)
    
    return {"status": "saved"}


@router.delete("/configs/{config_type}")
async def delete_config(
    config_type: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """Eliminar configuración del tenant - requiere auth"""
    db = get_database()
    # SEGURIDAD: filtrar por tenantId
    result = await db[COLLECTION_CONFIG].delete_one({"type": config_type, "tenantId": current_user.tenantId})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Config not found")
    return {"status": "deleted"}


# ============ LOG ENDPOINTS ============

@router.get("/logs", response_model=list[NotificationLogResponse])
async def list_logs(
    limit: int = 100,
    client_id: str = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """Listar logs de notificaciones del tenant"""
    db = get_database()
    # SEGURIDAD: filtrar por tenantId
    query = {"tenantId": current_user.tenantId}
    if client_id:
        query["clientId"] = client_id
    logs = await db[COLLECTION_LOGS].find(query).sort("sentAt", -1).to_list(limit)
    for log in logs:
        log["id"] = str(log.pop("_id"))
    return logs


@router.get("/logs/today")
async def get_today_logs(
    current_user: UserResponse = Depends(get_current_user)
):
    """Obtener logs de hoy del tenant"""
    db = get_database()
    # SEGURIDAD: filtrar por tenantId
    logs = await db[COLLECTION_LOGS].find({
        "tenantId": current_user.tenantId,
        "sentAt": {"$gte": datetime.utcnow().replace(hour=0, minute=0)}
    }).to_list(100)
    return logs


# ============ SEND ENDPOINT ============

@router.post("/send/manual")
async def send_manual_notification(
    client_id: str,
    message: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """Enviar notificación manual - requiere auth"""
    # SEGURIDAD: solo ADMIN o GERENTE pueden enviar notificaciones manuales
    if current_user.role.value not in ["ADMIN", "GERENTE"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para enviar notificaciones")
    return {
        "status": "sent",
        "client_id": client_id,
        "message": message,
        "tenantId": current_user.tenantId,
        "sent_at": datetime.utcnow().isoformat()
    }


# ============ SCHEDULER ENDPOINTS ============

@router.post("/scheduler/start")
async def start_scheduler(
    current_user: UserResponse = Depends(get_current_user)
):
    """Iniciar scheduler - solo GERENTE (owner)"""
    # SEGURIDAD: solo el owner puede iniciar/detener el scheduler
    if current_user.role.value != "GERENTE" or not current_user.isOwner:
        raise HTTPException(status_code=403, detail="Solo el owner puede gestionar el scheduler")
    from app.scheduler.jobs import start_scheduler as start
    start()
    return {"status": "started"}


@router.post("/scheduler/stop")
async def stop_scheduler(
    current_user: UserResponse = Depends(get_current_user)
):
    """Detener scheduler - solo GERENTE (owner)"""
    if current_user.role.value != "GERENTE" or not current_user.isOwner:
        raise HTTPException(status_code=403, detail="Solo el owner puede gestionar el scheduler")
    from app.scheduler.jobs import stop_scheduler as stop
    stop()
    return {"status": "stopped"}


@router.get("/scheduler/status")
async def get_scheduler_status(
    current_user: UserResponse = Depends(get_current_user)
):
    """Obtener estado del scheduler - requiere auth"""
    from app.scheduler.jobs import get_scheduler_status as status
    return status()