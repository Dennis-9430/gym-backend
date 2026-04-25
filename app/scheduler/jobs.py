# Jobs de scheduler para notificaciones WhatsApp
"""Notification scheduler jobs"""
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.database import db
from app.services.whatsapp import whatsapp_service
from app.models.tenant import TenantResponse
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

COLLECTION_CLIENTS = "clients"
COLLECTION_CONFIG = "notification_configs"
COLLECTION_LOGS = "notification_logs"
COLLECTION_TENANTS = "tenants"


async def get_active_clients_expiring(days_ahead: int = 3) -> list:
    """Obtener clientes con membresía por vencer"""
    target_date = datetime.utcnow() + timedelta(days=days_ahead)
    target_date_start = target_date.replace(hour=0, minute=0, second=0)
    target_date_end = target_date.replace(hour=23, minute=59, second=59)
    
    clients = await db[COLLECTION_CLIENTS].find({
        "membershipEndDate": {
            "$gte": target_date_start,
            "$lte": target_date_end
        },
        "membershipStatus": "ACTIVE"
    }).to_list(100)
    
    return clients


async def get_all_active_clients() -> list:
    """Obtener todos los clientes activos"""
    clients = await db[COLLECTION_CLIENTS].find({
        "membershipStatus": "ACTIVE"
    }).to_list(1000)
    return clients


async def has_been_sent_today(client_id: str, notification_type: str) -> bool:
    """Verificar si ya se envió notificación hoy"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
    
    log = await db[COLLECTION_LOGS].find_one({
        "clientId": client_id,
        "type": notification_type,
        "sentAt": {"$gte": today_start}
    })
    
    return log is not None


async def get_business_name() -> str:
    """Obtener nombre del negocio"""
    tenant = await db[COLLECTION_TENANTS].find_one({})
    if tenant:
        return tenant.get("businessName", "Tu Gimnasio")
    return "Tu Gimnasio"


async def log_notification(client_id: str, notification_type: str, message: str, status: str):
    """Registrar log de notificación"""
    await db[COLLECTION_LOGS].insert_one({
        "clientId": client_id,
        "type": notification_type,
        "message": message,
        "status": status,
        "sentAt": datetime.utcnow()
    })


async def run_expiry_job():
    """Job: Recordatorio de vencimiento (cron - 20:00 diario)"""
    logger.info("🔔 Ejecutando job de vencimiento...")
    
    # Obtener config
    config = await db[COLLECTION_CONFIG].find_one({"type": "expiry"})
    if not config or not config.get("enabled", True):
        logger.info("Job de vencimiento deshabilitado")
        return
    
    template = config.get("message", "")
    expiry_days = 3  # Días antes del vencimiento
    
    # Obtener clientes por vencer
    clients = await get_active_clients_expiring(expiry_days)
    
    if not clients:
        logger.info("No hay clientes por vencer")
        return
    
    business_name = await get_business_name()
    
    for client in clients:
        client_id = str(client.get("_id", ""))
        
        # Verificar duplicado
        if await has_been_sent_today(client_id, "expiry"):
            logger.info(f"Cliente {client_id} ya notificado hoy")
            continue
        
        # Preparar mensaje
        membership_end = client.get("membershipEndDate")
        fecha_str = membership_end.strftime("%d/%m/%Y") if membership_end else "pronto"
        
        variables = {
            "nombre": client.get("firstName", "Cliente"),
            "fecha": fecha_str,
            "negocio": business_name
        }
        
        message = whatsapp_service.format_message(template, variables)
        phone = client.get("phone", "")
        
        if not phone:
            logger.warning(f"Cliente {client_id} sin teléfono")
            await log_notification(client_id, "expiry", message, "failed")
            continue
        
        # Enviar
        result = await whatsapp_service.send_message(phone, message)
        
        status = result.get("status", "failed")
        await log_notification(client_id, "expiry", message, status)
        
        logger.info(f"Enviado a {client.get('firstName')}: {status}")
    
    # Marcar como enviado hoy
    await db[COLLECTION_CONFIG].update_one(
        {"type": "expiry"},
        {"$set": {"sentToday": True, "updatedAt": datetime.utcnow()}}
    )


async def run_scheduled_job():
    """Job: Mensajes programados (interval - cada 1 minuto)"""
    logger.info("⏰ Ejecutando job programado...")
    
    today = datetime.utcnow().date().isoformat()
    current_time = datetime.utcnow().strftime("%H:%M")
    
    # Obtener configs programadas para hoy
    configs = await db[COLLECTION_CONFIG].find({
        "type": "scheduled",
        "scheduledDate": today,
        "enabled": True
    }).to_list(10)
    
    if not configs:
        logger.info("No hay mensajes programados para hoy")
        return
    
    business_name = await get_business_name()
    clients = await get_all_active_clients()
    
    for config in configs:
        # Verificar si es la hora
        scheduled_time = config.get("scheduledTime", "")
        if scheduled_time != current_time:
            continue
        
        # Verificar si ya se envió
        if config.get("sentToday", False):
            logger.info(f"Msg programado ya enviado: {config.get('_id')}")
            continue
        
        template = config.get("message", "")
        
        # Enviar a todos los activos
        sent_count = 0
        for client in clients:
            client_id = str(client.get("_id", ""))
            
            variables = {
                "nombre": client.get("firstName", "Cliente"),
                "fecha": today,
                "negocio": business_name
            }
            
            message = whatsapp_service.format_message(template, variables)
            phone = client.get("phone", "")
            
            if not phone:
                continue
            
            result = await whatsapp_service.send_message(phone, message)
            await log_notification(client_id, "scheduled", message, result.get("status", "failed"))
            
            if result.get("status") == "success":
                sent_count += 1
        
        # Marcar como enviado
        await db[COLLECTION_CONFIG].update_one(
            {"_id": config["_id"]},
            {"$set": {"sentToday": True, "updatedAt": datetime.utcnow()}}
        )
        
        logger.info(f"Enviado {sent_count} mensajes programados")


def start_scheduler():
    """Iniciar el scheduler"""
    if scheduler.running:
        logger.info("Scheduler ya está corriendo")
        return
    
    # Job 1: Expiry - Diario a las 20:00
    scheduler.add_job(
        run_expiry_job,
        CronTrigger(hour=20, minute=0),
        id="expiry_job",
        replace_existing=True
    )
    
    # Job 2: Scheduled - Cada 1 minuto
    scheduler.add_job(
        run_scheduled_job,
        IntervalTrigger(minutes=1),
        id="scheduled_job",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ Scheduler iniciado")


def stop_scheduler():
    """Detener el scheduler"""
    if not scheduler.running:
        logger.info("Scheduler no está corriendo")
        return
    
    scheduler.shutdown()
    logger.info("🛑 Scheduler detenido")


def get_scheduler_status() -> dict:
    """Obtener estado del scheduler"""
    return {
        "running": scheduler.running,
        "jobs": [
            {"id": job.id, "next_run": str(job.next_run_time) if job.next_run_time else None}
            for job in scheduler.get_jobs()
        ]
    }