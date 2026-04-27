# Router para Notificaciones WhatsApp
# SEGURIDAD: Todos los endpoints requieren autenticación
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
from datetime import datetime

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

COLLECTION_CONFIG = "notification_configs"
COLLECTION_LOGS = "notification_logs"


# ============ CONFIG ENDPOINTS ============

@router.get("/configs", response_model=list[NotificationConfigResponse])
async def list_configs(current_user: UserResponse = Depends(get_current_user)):
    """Listar todas las configuraciones - requiere auth"""
    db = get_database()
    configs = await db[COLLECTION_CONFIG].find().to_list(100)
    for c in configs:
        c["_id"] = str(c["_id"])
    return configs


@router.get("/configs/{config_type}", response_model=NotificationConfigResponse)
async def get_config(config_type: str):
    """Obtener configuración por tipo"""
    db = get_database()
    config = await db[COLLECTION_CONFIG].find_one({"type": config_type})
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    config["_id"] = str(config["_id"])
    return config


@router.post("/configs")
async def create_or_update_config(config: NotificationConfigCreate):
    """Crear o actualizar configuración"""
    db = get_database()
    config_dict = config.model_dump()
    config_dict["updatedAt"] = datetime.utcnow()
    
    existing = await db[COLLECTION_CONFIG].find_one({"type": config.type})
    
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
async def delete_config(config_type: str):
    """Eliminar configuración"""
    db = get_database()
    result = await db[COLLECTION_CONFIG].delete_one({"type": config_type})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Config not found")
    return {"status": "deleted"}


# ============ LOG ENDPOINTS ============

@router.get("/logs", response_model=list[NotificationLogResponse])
async def list_logs(limit: int = 100, client_id: str = None):
    """Listar logs de notificaciones"""
    db = get_database()
    query = {"clientId": client_id} if client_id else {}
    logs = await db[COLLECTION_LOGS].find(query).sort("sentAt", -1).to_list(limit)
    for log in logs:
        log["_id"] = str(log["_id"])
    return logs


@router.get("/logs/today")
async def get_today_logs():
    """Obtener logs de hoy"""
    db = get_database()
    logs = await db[COLLECTION_LOGS].find({
        "sentAt": {"$gte": datetime.utcnow().replace(hour=0, minute=0)}
    }).to_list(100)
    return logs


# ============ SEND ENDPOINT ============

@router.post("/send/manual")
async def send_manual_notification(client_id: str, message: str):
    """Enviar notificación manual (para testing)"""
    return {
        "status": "sent",
        "client_id": client_id,
        "message": message,
        "sent_at": datetime.utcnow().isoformat()
    }


# ============ SCHEDULER ENDPOINTS ============

@router.post("/scheduler/start")
async def start_scheduler():
    """Iniciar scheduler"""
    from app.scheduler.jobs import start_scheduler as start
    start()
    return {"status": "started"}


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Detener scheduler"""
    from app.scheduler.jobs import stop_scheduler as stop
    stop()
    return {"status": "stopped"}


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Obtener estado del scheduler"""
    from app.scheduler.jobs import get_scheduler_status as status
    return status()