# Jobs de scheduler para notificaciones WhatsApp
"""Notification scheduler jobs"""
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.database import get_database
from app.services.whatsapp import whatsapp_service
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

COLLECTION_CLIENTS = "clients"
COLLECTION_CONFIG = "notification_configs"
COLLECTION_LOGS = "notification_logs"
COLLECTION_TENANTS = "tenants"


async def get_active_clients_expiring(tenant_id: str, days_ahead: int = 3) -> list:
    """Obtener clientes del tenant con membresía por vencer."""
    db = get_database()
    target_date = datetime.utcnow() + timedelta(days=days_ahead)
    target_date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    target_date_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    return await db[COLLECTION_CLIENTS].find({
        "tenantId": tenant_id,
        "membershipEndDate": {"$gte": target_date_start, "$lte": target_date_end},
        "membershipStatus": "ACTIVE"
    }).to_list(100)


async def get_all_active_clients(tenant_id: str) -> list:
    """Obtener todos los clientes activos del tenant."""
    db = get_database()
    return await db[COLLECTION_CLIENTS].find({
        "tenantId": tenant_id,
        "membershipStatus": "ACTIVE"
    }).to_list(1000)


async def has_been_sent_today(tenant_id: str, client_id: str, notification_type: str) -> bool:
    """Verificar si ya se envió notificación hoy para ese tenant y cliente."""
    db = get_database()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    log = await db[COLLECTION_LOGS].find_one({
        "tenantId": tenant_id,
        "clientId": client_id,
        "type": notification_type,
        "sentAt": {"$gte": today_start}
    })
    return log is not None


async def get_business_name(tenant_id: str) -> str:
    """Obtener nombre del negocio por tenant."""
    db = get_database()
    tenant = await db[COLLECTION_TENANTS].find_one({"tenantId": tenant_id})
    if tenant:
        return tenant.get("businessName", "Tu Gimnasio")
    return "Tu Gimnasio"


async def log_notification(tenant_id: str, client_id: str, notification_type: str, message: str, status: str):
    """Registrar log de notificación con tenantId."""
    db = get_database()
    await db[COLLECTION_LOGS].insert_one({
        "tenantId": tenant_id,
        "clientId": client_id,
        "type": notification_type,
        "message": message,
        "status": status,
        "sentAt": datetime.utcnow()
    })


async def run_expiry_job():
    """Job: Recordatorio de vencimiento (cron - 20:00 diario) por tenant."""
    logger.info("Ejecutando job de vencimiento...")
    db = get_database()

    configs = await db[COLLECTION_CONFIG].find({
        "type": "expiry",
        "enabled": True
    }).to_list(500)

    if not configs:
        logger.info("No hay configuraciones de vencimiento activas")
        return

    for config in configs:
        tenant_id = config.get("tenantId")
        if not tenant_id:
            continue

        template = config.get("message", "")
        expiry_days = 3
        clients = await get_active_clients_expiring(tenant_id, expiry_days)
        if not clients:
            continue

        business_name = await get_business_name(tenant_id)

        for client in clients:
            client_id = str(client.get("_id", ""))
            if await has_been_sent_today(tenant_id, client_id, "expiry"):
                continue

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
                await log_notification(tenant_id, client_id, "expiry", message, "failed")
                continue

            result = await whatsapp_service.send_message(phone, message)
            status = result.get("status", "failed")
            await log_notification(tenant_id, client_id, "expiry", message, status)

        await db[COLLECTION_CONFIG].update_one(
            {"_id": config["_id"]},
            {"$set": {"sentToday": True, "updatedAt": datetime.utcnow()}}
        )


async def run_scheduled_job():
    """Job: Mensajes programados (interval - cada 1 minuto) por tenant."""
    logger.info("Ejecutando job programado...")
    db = get_database()

    today = datetime.utcnow().date().isoformat()
    current_time = datetime.utcnow().strftime("%H:%M")

    configs = await db[COLLECTION_CONFIG].find({
        "type": "scheduled",
        "scheduledDate": today,
        "enabled": True
    }).to_list(500)

    if not configs:
        return

    for config in configs:
        tenant_id = config.get("tenantId")
        if not tenant_id:
            continue

        scheduled_time = config.get("scheduledTime", "")
        if scheduled_time != current_time or config.get("sentToday", False):
            continue

        business_name = await get_business_name(tenant_id)
        clients = await get_all_active_clients(tenant_id)
        template = config.get("message", "")

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
            await log_notification(tenant_id, client_id, "scheduled", message, result.get("status", "failed"))
            if result.get("status") == "success":
                sent_count += 1

        await db[COLLECTION_CONFIG].update_one(
            {"_id": config["_id"]},
            {"$set": {"sentToday": True, "updatedAt": datetime.utcnow()}}
        )
        logger.info("Tenant %s: enviados %s mensajes programados", tenant_id, sent_count)


def start_scheduler():
    """Iniciar el scheduler."""
    if scheduler.running:
        logger.info("Scheduler ya está corriendo")
        return

    scheduler.add_job(
        run_expiry_job,
        CronTrigger(hour=20, minute=0),
        id="expiry_job",
        replace_existing=True
    )

    scheduler.add_job(
        run_scheduled_job,
        IntervalTrigger(minutes=1),
        id="scheduled_job",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler iniciado")


def stop_scheduler():
    """Detener el scheduler."""
    if not scheduler.running:
        logger.info("Scheduler no está corriendo")
        return

    scheduler.shutdown()
    logger.info("Scheduler detenido")


def get_scheduler_status() -> dict:
    """Obtener estado del scheduler."""
    return {
        "running": scheduler.running,
        "jobs": [
            {"id": job.id, "next_run": str(job.next_run_time) if job.next_run_time else None}
            for job in scheduler.get_jobs()
        ]
    }
