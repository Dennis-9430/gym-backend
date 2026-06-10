#!/usr/bin/env python3
"""
Script de migración de índices — ejecutar UNA SOLA VEZ por deploy.

Uso:
    cd backend
    python scripts/migrate_indexes.py              # ejecutar migración
    python scripts/migrate_indexes.py --dry-run     # solo listar lo que haría, sin modificar

Este script reemplaza la creación automática de índices en startup.
NO debe ejecutarse desde lifespan() — solo manualmente en cada deploy.

Relacionado con: app/database.py (create_indexes)
"""
import asyncio
import argparse
import logging
import sys
import os

# Asegurar que el directorio backend esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate_indexes")


def _infer_index_name(keys):
    """Genera el nombre de índice por defecto que MongoDB asignaría."""
    if isinstance(keys, str):
        return f"{keys}_1"
    if isinstance(keys, list):
        return "_".join(f"{k[0]}_{k[1]}" for k in keys)
    return None


class Collections:
    TENANTS = "tenants"
    USERS = "users"
    EMPLOYEES = "employees"
    CLIENTS = "clients"
    PRODUCTS = "products"
    SALES = "sales"
    ATTENDANCE = "attendance"
    SERVICES = "services"
    INVOICES = "invoices"
    COUNTERS = "counters"


async def migrate(dry_run: bool = False):
    """Ejecuta la migración de índices."""
    logger.info("Conectando a MongoDB: %s", settings.MONGODB_URL)
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]

    # Verificar conexión
    await client.admin.command("ping")
    logger.info("Conexión exitosa a MongoDB")

    index_configs = [
        (db[Collections.TENANTS], "tenantId", True),
        (db[Collections.TENANTS], "email", True),
        (db[Collections.TENANTS], "businessCode", True),
        (db[Collections.USERS], "username", False),
        (db[Collections.USERS], [("tenantId", 1), ("username", 1)], True),
        (db[Collections.EMPLOYEES], [("tenantId", 1), ("username", 1)], True),
        (db[Collections.CLIENTS], [("tenantId", 1), ("documentNumber", 1)], True),
        (db[Collections.PRODUCTS], [("tenantId", 1), ("code", 1)], True),
        (db[Collections.SERVICES], [("tenantId", 1), ("name", 1)], True),
        (db[Collections.USERS], [("tenantId", 1), ("employeeId", 1)], False),
        (db[Collections.INVOICES], [("tenantId", 1), ("invoiceNumber", 1)], True),
        (db[Collections.INVOICES], [("tenantId", 1), ("createdAt", -1)], False),
        (db[Collections.SALES], [("tenantId", 1), ("createdAt", -1)], False),
        (db[Collections.ATTENDANCE], [("tenantId", 1), ("clientId", 1), ("checkIn", -1)], False),
        (db[Collections.COUNTERS], [("tenantId", 1)], True),
        (db["notification_configs"], [("tenantId", 1), ("type", 1)], True),
        (db["notification_logs"], [("tenantId", 1), ("clientId", 1), ("sentAt", -1)], False),
        (db[Collections.TENANT_PAYMENTS], [("createdAt", 1)], False),  # monthly revenue aggregation
        (db[Collections.TENANTS], [("subscriptionStatus", 1)], False),  # count_documents by status
        (db[Collections.TENANTS], [("subscriptionStatus", 1), ("subscriptionEndDate", 1)], False),  # expiring soon query
        (db["audit_logs"], [("tenantId", 1), ("timestamp", -1)], False),
        (db["audit_logs"], [("event", 1), ("timestamp", -1)], False),
        (db["audit_logs"], [("actor_id", 1), ("timestamp", -1)], False),
    ]

    if dry_run:
        logger.info("")
        logger.info("=== MODO DRY-RUN — no se modifica nada ===")
        for collection, keys, unique in index_configs:
            index_name = _infer_index_name(keys)
            existing = await collection.index_information()
            status = "✅ ya existe" if index_name in existing else "❌ FALTANTE"
            logger.info("  %s %s.%s (unique=%s)", status, collection.name, keys, unique)
        client.close()
        logger.info("")
        logger.info("Dry-run completado. Ejecutá sin --dry-run para aplicar.")
        return

    success_count = 0
    error_count = 0

    for collection, keys, unique in index_configs:
        try:
            await collection.create_index(keys, unique=unique, background=True)
            logger.info("  ✅ %s.%s (unique=%s)", collection.name, keys, unique)
            success_count += 1
        except Exception as e:
            err_str = str(e).lower()
            err_code = getattr(e, "code", None)

            # Error 86: IndexKeySpecsConflict — el índice existe con otro nombre/opciones
            if err_code == 86:
                index_name = _infer_index_name(keys)
                try:
                    await collection.drop_index(index_name)
                    await collection.create_index(keys, unique=unique, background=True)
                    logger.info("  ♻️  %s.%s reemplazado (conflicto resuelto)", collection.name, keys)
                    success_count += 1
                except Exception as drop_err:
                    logger.error("  ❌ %s.%s: no se pudo reemplazar: %s", collection.name, keys, drop_err)
                    error_count += 1
                continue

            if "duplicate" in err_str and unique:
                logger.warning("  ⚠️  %s.%s: datos duplicados, índice único no creado", collection.name, keys)
                continue

            logger.error("  ❌ %s.%s: %s", collection.name, keys, e)
            error_count += 1

    client.close()

    logger.info("")
    logger.info("=== Resumen ===")
    logger.info("  Creados/verificados: %d", success_count)
    logger.info("  Errores: %d", error_count)

    if error_count > 0:
        logger.warning("  Revisá los errores antes de continuar con el deploy.")
        sys.exit(1)
    else:
        logger.info("  Migración completada exitosamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migración de índices MongoDB")
    parser.add_argument("--dry-run", action="store_true", help="Solo listar índices faltantes sin crear nada")
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run))
