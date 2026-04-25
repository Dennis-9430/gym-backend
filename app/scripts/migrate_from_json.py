"""
Script de migracion localStorage -> MongoDB
Ejecutar desde backend/ con: python -m app.scripts.migrate_from_json
"""
import json
import asyncio
from datetime import datetime
from app.database import connect_to_mongodb, get_database, Collections


async def migrate_clients(db):
    """Migra clientes desde JSON exportado"""
    try:
        with open("app/scripts/data/clients.json", "r", encoding="utf-8") as f:
            clients = json.load(f)
    except FileNotFoundError:
        print("  app/scripts/data/clients.json no encontrado")
        return 0
    
    migrated = 0
    for client in clients:
        doc = {
            "tenantId": "demo-gym",
            "documentType": client.get("documentType", "CEDULA"),
            "documentNumber": client.get("documentNumber"),
            "firstName": client.get("firstName"),
            "lastName": client.get("lastName"),
            "phone": client.get("phone", ""),
            "email": client.get("email", ""),
            "address": client.get("address", ""),
            "emergencyContact": client.get("emergencyContact", ""),
            "emergencyPhone": client.get("emergencyPhone", ""),
            "notes": client.get("notes", ""),
            "membership": client.get("memberShip", "Por registrar"),
            "membershipStatus": client.get("memberShipStatus", "NONE"),
            "fingerprint": client.get("fingerPrint", False),
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await db[Collections.CLIENTS].insert_one(doc)
        migrated += 1
    
    print(f"  OK {migrated} clientes migrados")
    return migrated


async def migrate_products(db):
    """Migra productos desde JSON exportado"""
    try:
        with open("app/scripts/data/products.json", "r", encoding="utf-8") as f:
            products = json.load(f)
    except FileNotFoundError:
        print("  app/scripts/data/products.json no encontrado")
        return 0
    
    migrated = 0
    for prod in products:
        doc = {
            "tenantId": "demo-gym",
            "code": prod.get("code"),
            "name": prod.get("name"),
            "description": prod.get("description", ""),
            "category": prod.get("category"),
            "unitPrice": prod.get("unitPrice", 0),
            "stock": prod.get("quantity", 0),
            "minStock": prod.get("minStock", 0),
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await db[Collections.PRODUCTS].insert_one(doc)
        migrated += 1
    
    print(f"  [OK] {migrated} productos migrados")
    return migrated


async def migrate_sales(db):
    """Migra ventas desde JSON exportado"""
    try:
        with open("app/scripts/data/sales.json", "r", encoding="utf-8") as f:
            sales = json.load(f)
    except FileNotFoundError:
        print("  app/scripts/data/sales.json no encontrado")
        return 0
    
    migrated = 0
    for sale in sales:
        doc = {
            "tenantId": "demo-gym",
            "createdAt": sale.get("createdAt"),
            "items": sale.get("items", []),
            "totals": sale.get("totals", {}),
            "client": sale.get("client", {}),
            "payment": sale.get("payment", {}),
            "voucherCode": sale.get("voucherCode", ""),
            "createdBy": sale.get("createdBy", "Sistema"),
        }
        await db[Collections.SALES].insert_one(doc)
        migrated += 1
    
    print(f"  [OK] {migrated} ventas migradas")
    return migrated


async def migrate_services(db):
    """Migra servicios/membresias desde JSON exportado"""
    try:
        with open("app/scripts/data/services.json", "r", encoding="utf-8") as f:
            services = json.load(f)
    except FileNotFoundError:
        print("  app/scripts/data/services.json no encontrado")
        return 0
    
    migrated = 0
    for svc in services:
        doc = {
            "tenantId": "demo-gym",
            "name": svc.get("name"),
            "description": svc.get("description", ""),
            "price": svc.get("price", 0),
            "duration": svc.get("duration", 30),
            "durationType": svc.get("durationType", "days"),
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await db[Collections.SERVICES].insert_one(doc)
        migrated += 1
    
    print(f"  [OK] {migrated} servicios migrados")
    return migrated


async def run_migration():
    """Ejecuta la migracion completa"""
    print("=" * 40)
    print("  Migracion localStorage -> MongoDB")
    print("=" * 40)
    
    await connect_to_mongodb()
    db = get_database()
    
    print("\n[1] Clientes")
    await migrate_clients(db)
    
    print("\n[2] Productos")
    await migrate_products(db)
    
    print("\n[3] Ventas")
    await migrate_sales(db)
    
    print("\n[4] Servicios/Membresias")
    await migrate_services(db)
    
    print("\n" + "=" * 40)
    print("  Migracion completada!")
    print("=" * 40)
    
    # Mostrar totals
    print("\nTotales en MongoDB:")
    print(f"  Clientes:   {await db[Collections.CLIENTS].count_documents({})}")
    print(f"  Productos: {await db[Collections.PRODUCTS].count_documents({})}")
    print(f"  Ventas:    {await db[Collections.SALES].count_documents({})}")
    print(f"  Servicios: {await db[Collections.SERVICES].count_documents({})}")


if __name__ == "__main__":
    asyncio.run(run_migration())