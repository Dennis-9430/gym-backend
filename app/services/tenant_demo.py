"""TenantDemoService — demo tenant initialization, seeding, and cleanup.

Extracted from app/routers/tenants.py (initialize_tenant_demo, create_default_services,
seed_demo_data, seed_demo_attendance, seed_demo_owner) and app/routers/demo.py
(cleanup_demo_data).

PURE REFACTOR — logic is identical to the original. Only change is:
  db. → self.db.  (constructor-injected database instance)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import Collections
from app.models.tenant import SubscriptionPlan, SubscriptionStatus

logger = logging.getLogger(__name__)


class TenantDemoService:
    """Service for demo tenant lifecycle: initialize, seed data, cleanup.

    Constructor receives the database instance for testability.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def initialize(self) -> None:
        """Create demo tenant if not exists.

        Orchestrates creation/migration of demo-basic and demo-premium tenants,
        including default services, seed data, attendance, and owner.
        """
        from app.models.tenant import SubscriptionPlan, SubscriptionStatus
        from app.models.service import ServiceType
        from app.auth.utils import get_password_hash

        demo_password_hash = get_password_hash("demo123456")

        # ── Demo BASIC ─────────────────────────────────────────────────────
        existing_basic = await self.db.tenants.find_one({"tenantId": "demo-basic-001"})
        if not existing_basic:
            demo_basic = {
                "tenantId": "demo-basic-001",
                "businessCode": "demo-basic",
                "email": "demo-basic@gmail.com",
                "password": demo_password_hash,
                "businessName": "Gimnasio Demo Basic",
                "businessPhone": "",
                "businessAddress": "",
                "businessRuc": "",
                "plan": SubscriptionPlan.BASIC,
                "subscriptionStatus": SubscriptionStatus.ACTIVE,
                "subscriptionEndDate": None,
                "taxRate": 12.0,
                "currency": "USD",
                "openingHour": "06:00",
                "closingHour": "22:00",
                "wsspReminderDays": 3,
                "wsspEnabled": False,
                "isDemo": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            await self.db.tenants.insert_one(demo_basic)
            await self.create_default_services("demo-basic-001")
        else:
            ops = {}
            if not existing_basic.get("isDemo"):
                ops["isDemo"] = True
            if not existing_basic.get("businessCode"):
                ops["businessCode"] = "demo-basic"
            ops["password"] = demo_password_hash
            if ops:
                await self.db.tenants.update_one(
                    {"tenantId": "demo-basic-001"},
                    {"$set": ops},
                )

        await self.create_default_services("demo-basic-001")
        await self.seed_data("demo-basic-001")
        await self.seed_attendance("demo-basic-001")
        await self.seed_owner("demo-basic-001", "demo-basic@gmail.com", "Gimnasio Demo Basic")

        # ── Demo PRO ───────────────────────────────────────────────────────
        existing_pro = await self.db.tenants.find_one({"tenantId": "demo-pro-001"})
        if not existing_pro:
            demo_pro = {
                "tenantId": "demo-pro-001",
                "businessCode": "demo-premium",
                "email": "demo-pro@gmail.com",
                "password": demo_password_hash,
                "businessName": "Gimnasio Demo Pro",
                "businessPhone": "",
                "businessAddress": "",
                "businessRuc": "",
                "plan": SubscriptionPlan.PREMIUM,
                "subscriptionStatus": SubscriptionStatus.ACTIVE,
                "subscriptionEndDate": None,
                "taxRate": 12.0,
                "currency": "USD",
                "openingHour": "06:00",
                "closingHour": "22:00",
                "wsspReminderDays": 3,
                "wsspEnabled": False,
                "isDemo": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            await self.db.tenants.insert_one(demo_pro)
            await self.create_default_services("demo-pro-001")
        else:
            ops = {}
            if not existing_pro.get("isDemo"):
                ops["isDemo"] = True
            if not existing_pro.get("businessCode"):
                ops["businessCode"] = "demo-premium"
            ops["password"] = demo_password_hash
            if ops:
                await self.db.tenants.update_one(
                    {"tenantId": "demo-pro-001"},
                    {"$set": ops},
                )

        await self.create_default_services("demo-pro-001")
        await self.seed_data("demo-pro-001")
        await self.seed_attendance("demo-pro-001")
        await self.seed_owner("demo-pro-001", "demo-pro@gmail.com", "Gimnasio Demo Pro")

    async def create_default_services(self, tenant_id: str) -> None:
        """Crea los servicios default para un tenant."""
        from app.models.service import ServiceType

        default_services = [
            {
                "tenantId": tenant_id,
                "name": "Pago Diario",
                "description": "Acceso al gimnasio por un día",
                "price": 2.50,
                "duration": 1,
                "durationUnit": "days",
                "type": ServiceType.DAILY.value,
                "isActive": True,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            },
            {
                "tenantId": tenant_id,
                "name": "Día de Prueba",
                "description": "Acceso de prueba por un día",
                "price": 2.00,
                "duration": 1,
                "durationUnit": "days",
                "type": ServiceType.DAILY.value,
                "isActive": True,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            },
            {
                "tenantId": tenant_id,
                "name": "Quincenal",
                "description": "Membresía quincenal",
                "price": 18.00,
                "duration": 15,
                "durationUnit": "days",
                "type": ServiceType.MEMBERSHIP.value,
                "isActive": True,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            },
            {
                "tenantId": tenant_id,
                "name": "Mensual",
                "description": "Membresía mensual completa",
                "price": 30.00,
                "duration": 30,
                "durationUnit": "days",
                "type": ServiceType.MEMBERSHIP.value,
                "isActive": True,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            },
        ]

        for service_data in default_services:
            existing = await self.db.services.find_one(
                {"tenantId": tenant_id, "name": service_data["name"]},
            )
            if not existing:
                await self.db.services.insert_one(service_data)

    async def seed_data(self, tenant_id: str) -> None:
        """Crea datos semilla fijos para tenants demo.

        Estos datos tienen isSeed=True y NO son eliminados por el cleanup.
        Es IDEMPOTENTE: si ya existen productos seed para este tenant, no hace nada.
        """
        from app.models.service import ServiceType

        # Verificar si ya existen datos seed para este tenant
        existing_seed = await self.db.products.find_one({"tenantId": tenant_id, "isSeed": True})
        if existing_seed:
            return

        # ============================================================
        # 1. PRODUCTOS (10 con precios variados)
        # ============================================================
        products_data = [
            {"code": "BAR001", "name": "Barra Proteica", "description": "Barra de proteína 30g", "category": "Nutrición", "unitPrice": 2.50, "stock": 50, "minStock": 10},
            {"code": "BEB001", "name": "Bebida Energética", "description": "Bebida isotónica 500ml", "category": "Nutrición", "unitPrice": 3.00, "stock": 40, "minStock": 10},
            {"code": "TOA001", "name": "Toalla Deportiva", "description": "Toalla microfibra 60x30cm", "category": "Accesorios", "unitPrice": 15.00, "stock": 20, "minStock": 5},
            {"code": "SHA001", "name": "Shaker", "description": "Shaker 600ml con mezclador", "category": "Accesorios", "unitPrice": 8.00, "stock": 30, "minStock": 5},
            {"code": "CUE001", "name": "Cuerda para Saltar", "description": "Cuerda ajustable con rodamientos", "category": "Equipamiento", "unitPrice": 12.00, "stock": 15, "minStock": 3},
            {"code": "BAN001", "name": "Bandas de Resistencia", "description": "Set de 5 bandas de diferente intensidad", "category": "Equipamiento", "unitPrice": 20.00, "stock": 15, "minStock": 3},
            {"code": "GUA001", "name": "Guantes de Gimnasio", "description": "Guantes con soporte de muñeca", "category": "Accesorios", "unitPrice": 25.00, "stock": 12, "minStock": 3},
            {"code": "MAT001", "name": "Mat de Yoga", "description": "Mat antideslizante 6mm", "category": "Equipamiento", "unitPrice": 35.00, "stock": 10, "minStock": 2},
            {"code": "BOL001", "name": "Bolso Deportivo", "description": "Bolso impermeable 40L", "category": "Accesorios", "unitPrice": 45.00, "stock": 8, "minStock": 2},
            {"code": "SUP001", "name": "Pack Suplementos", "description": "Combo proteína + creatina + BCAA", "category": "Nutrición", "unitPrice": 60.00, "stock": 5, "minStock": 1},
        ]

        product_ids = {}
        for p in products_data:
            doc = {
                **p,
                "tenantId": tenant_id,
                "taxRate": 0.0,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            result = await self.db.products.insert_one(doc)
            product_ids[p["code"]] = str(result.inserted_id)

        # ============================================================
        # 2. CLIENTES (2 recién registrados sin membresía + 2 activos)
        # ============================================================
        clients_data = [
            {
                "documentType": "CEDULA", "documentNumber": "0000000000",
                "firstName": "Carlos", "lastName": "López",
                "phone": None, "email": None, "address": None,
                "membership": "Por registrar", "membershipStatus": "NONE",
                "notes": "Cliente recién registrado, sin membresía asignada",
            },
            {
                "documentType": "CEDULA", "documentNumber": "0000000001",
                "firstName": "Ana", "lastName": "Martínez",
                "phone": None, "email": None, "address": None,
                "membership": "Por registrar", "membershipStatus": "NONE",
                "notes": "Cliente recién registrado, sin membresía asignada",
            },
            {
                "documentType": "CEDULA", "documentNumber": "1234567890",
                "firstName": "Juan", "lastName": "Pérez",
                "phone": "0991234567", "email": "juan.perez@email.com",
                "address": "Av. Principal 123",
                "membership": "Mensual", "membershipStatus": "ACTIVE",
                "membershipStartDate": datetime.utcnow(),
                "membershipEndDate": datetime(2026, 6, 9),
            },
            {
                "documentType": "CEDULA", "documentNumber": "0987654321",
                "firstName": "María", "lastName": "García",
                "phone": "0997654321", "email": "maria.garcia@email.com",
                "address": "Calle Secundaria 456",
                "membership": "Pago Diario", "membershipStatus": "ACTIVE",
                "membershipStartDate": datetime.utcnow(),
                "membershipEndDate": datetime.utcnow() + timedelta(days=1),
            },
        ]

        client_ids = {}
        for c in clients_data:
            doc = {
                **c,
                "tenantId": tenant_id,
                "fingerPrint": False,
                "emergencyContact": None,
                "emergencyPhone": None,
                "notes": None,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
            }
            result = await self.db.clients.insert_one(doc)
            client_ids[c["firstName"]] = str(result.inserted_id)

        # ============================================================
        # 3. SERVICIOS (referencias para ventas)
        # ============================================================
        daily_service = await self.db.services.find_one({"tenantId": tenant_id, "name": "Pago Diario"})
        monthly_service = await self.db.services.find_one({"tenantId": tenant_id, "name": "Mensual"})
        daily_service_id = str(daily_service["_id"]) if daily_service else None
        monthly_service_id = str(monthly_service["_id"]) if monthly_service else None

        # ============================================================
        # 4. VENTAS - Historial para clientes activos
        # ============================================================
        sales_seed = [
            # Juan Pérez: Mensual ($30) + Barra Proteica ($2.50)
            {
                "items": [
                    {"productName": "Mensual", "description": "Membresía mensual", "quantity": 1, "unitPrice": 30.00, "subtotal": 30.00, "source": "MEMBERSHIP", "serviceId": monthly_service_id},
                    {"productName": "Barra Proteica", "description": "", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50, "source": "PRODUCT", "productId": product_ids.get("BAR001")},
                ],
                "subtotal": 32.50, "total": 32.50,
                "clientName": "Juan Pérez", "clientId": client_ids.get("Juan"),
                "cashAmount": 32.50, "paymentMethod": "CASH",
            },
            # María García: Pago Diario ($2.50) + Bebida Energética ($3.00)
            {
                "items": [
                    {"productName": "Pago Diario", "description": "Acceso por un día", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50, "source": "DAILY", "serviceId": daily_service_id},
                    {"productName": "Bebida Energética", "description": "", "quantity": 1, "unitPrice": 3.00, "subtotal": 3.00, "source": "PRODUCT", "productId": product_ids.get("BEB001")},
                ],
                "subtotal": 5.50, "total": 5.50,
                "clientName": "María García", "clientId": client_ids.get("María"),
                "cashAmount": 5.50, "paymentMethod": "CASH",
            },
            # 2 membresías diarias extra
            {
                "items": [
                    {"productName": "Pago Diario", "description": "Acceso por un día", "quantity": 2, "unitPrice": 2.50, "subtotal": 5.00, "source": "DAILY", "serviceId": daily_service_id},
                ],
                "subtotal": 5.00, "total": 5.00,
                "clientName": "Venta Directa", "cashAmount": 5.00, "paymentMethod": "CASH",
            },
            # 2 ventas de productos extra
            {
                "items": [
                    {"productName": "Toalla Deportiva", "description": "", "quantity": 1, "unitPrice": 15.00, "subtotal": 15.00, "source": "PRODUCT", "productId": product_ids.get("TOA001")},
                ],
                "subtotal": 15.00, "total": 15.00,
                "clientName": "Venta Directa", "cashAmount": 15.00, "paymentMethod": "CASH",
            },
            {
                "items": [
                    {"productName": "Shaker", "description": "", "quantity": 2, "unitPrice": 8.00, "subtotal": 16.00, "source": "PRODUCT", "productId": product_ids.get("SHA001")},
                ],
                "subtotal": 16.00, "total": 16.00,
                "clientName": "Venta Directa", "cashAmount": 16.00, "paymentMethod": "CASH",
            },
            # Renovación mensual pendiente (para Juan Pérez, el cliente mensual activo)
            {
                "items": [
                    {"productName": "Mensual", "description": "Renovación mensual - Pendiente", "quantity": 1, "unitPrice": 30.00, "subtotal": 30.00, "source": "MEMBERSHIP", "serviceId": monthly_service_id},
                ],
                "subtotal": 30.00, "total": 30.00,
                "clientName": "Juan Pérez",
                "clientId": client_ids.get("Juan"),
                "cashAmount": 0.0, "paymentMethod": "TRANSFER", "paymentStatus": "pending",
                "voucherCode": "PEND-001",
            },
        ]

        sale_ids = []
        for i, s in enumerate(sales_seed):
            doc = {
                **s,
                "tenantId": tenant_id,
                "tax": 0.0,
                "paymentStatus": s.get("paymentStatus", "verified"),
                "transferAmount": 0.0,
                "clientFirstName": None, "clientLastName": None,
                "clientDocument": None, "clientEmail": None,
                "clientPhone": None, "clientAddress": None,
                "generateInvoice": False, "invoiceEmail": None,
                "createdBy": "demo-basic@gmail.com",
                "createdAt": datetime.utcnow() - timedelta(hours=i * 2),
                "isSeed": True,
            }
            if not doc.get("paymentStatus"):
                doc["paymentStatus"] = "verified"
            result = await self.db.sales.insert_one(doc)
            sale_ids.append(str(result.inserted_id))

        # ============================================================
        # 5. FACTURAS
        # ============================================================
        tenant_doc = await self.db.tenants.find_one({"tenantId": tenant_id})
        business = {
            "name": tenant_doc.get("businessName", "Gimnasio Demo"),
            "ruc": tenant_doc.get("businessRuc", "9999999999001"),
            "address": tenant_doc.get("businessAddress", "Dirección del gimnasio"),
            "phone": tenant_doc.get("businessPhone", "0999999999"),
            "email": tenant_doc.get("email", "demo@gimnasio.com"),
        }

        invoices_seed = [
            {
                "type": "MEMBERSHIP",
                "client": {"documentNumber": "1234567890", "firstName": "Juan", "lastName": "Pérez", "email": "juan.perez@email.com"},
                "items": [
                    {"name": "Mensual", "quantity": 1, "unitPrice": 30.00, "subtotal": 30.00},
                    {"name": "Barra Proteica", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50},
                ],
                "totals": {"subtotal": 32.50, "total": 32.50},
                "payment": {"method": "CASH", "cashAmount": 32.50, "paid": 32.50},
            },
            {
                "type": "MEMBERSHIP",
                "client": {"documentNumber": "0987654321", "firstName": "María", "lastName": "García", "email": "maria.garcia@email.com"},
                "items": [
                    {"name": "Pago Diario", "quantity": 1, "unitPrice": 2.50, "subtotal": 2.50},
                    {"name": "Bebida Energética", "quantity": 1, "unitPrice": 3.00, "subtotal": 3.00},
                ],
                "totals": {"subtotal": 5.50, "total": 5.50},
                "payment": {"method": "CASH", "cashAmount": 5.50, "paid": 5.50},
            },
            {
                "type": "PRODUCT",
                "client": {"documentNumber": "9999999999", "firstName": "Proveedor", "lastName": "Mayorista", "email": "proveedor@email.com"},
                "items": [
                    {"name": "Barra Proteica", "quantity": 20, "unitPrice": 1.50, "subtotal": 30.00},
                    {"name": "Bebida Energética", "quantity": 15, "unitPrice": 2.00, "subtotal": 30.00},
                    {"name": "Toalla Deportiva", "quantity": 10, "unitPrice": 8.00, "subtotal": 80.00},
                    {"name": "Shaker", "quantity": 10, "unitPrice": 4.00, "subtotal": 40.00},
                ],
                "totals": {"subtotal": 180.00, "total": 180.00},
                "payment": {"method": "TRANSFER", "cashAmount": 0.0, "transferAmount": 180.00, "paid": 180.00, "voucherCode": "FAC-PROV-001"},
            },
        ]

        for inv_data in invoices_seed:
            doc = {
                "tenantId": tenant_id,
                "type": inv_data["type"],
                "invoiceNumber": f"DEMO-{inv_data['type'][:4]}-{datetime.now().year}-{len(invoices_seed):06d}",
                "business": business,
                "client": inv_data["client"],
                "items": inv_data["items"],
                "totals": inv_data["totals"],
                "payment": inv_data["payment"],
                "status": "GENERATED",
                "createdBy": "demo-basic@gmail.com",
                "createdAt": datetime.utcnow(),
                "isSeed": True,
            }
            await self.db.invoices.insert_one(doc)

    async def seed_attendance(self, tenant_id: str) -> None:
        """Crea registros de asistencia demo. Independiente del seed de productos."""
        # Verificar si ya existen asistencias seed
        existing_att = await self.db.attendance.find_one({"tenantId": tenant_id, "isSeed": True})
        if existing_att:
            return

        # Crear clientes demo si no existen (para tenants existentes que ya tenían productos)
        demo_clients_data = [
            {"firstName": "Juan", "lastName": "Pérez", "documentType": "CEDULA", "documentNumber": "SEED-ATT-001"},
            {"firstName": "María", "lastName": "García", "documentType": "CEDULA", "documentNumber": "SEED-ATT-002"},
            {"firstName": "Carlos", "lastName": "López", "documentType": "CEDULA", "documentNumber": "SEED-ATT-003"},
            {"firstName": "Ana", "lastName": "Martínez", "documentType": "CEDULA", "documentNumber": "SEED-ATT-004"},
        ]

        client_map = {}
        for i, c in enumerate(demo_clients_data, start=1):
            existing = await self.db.clients.find_one(
                {"tenantId": tenant_id, "firstName": c["firstName"], "lastName": c["lastName"]},
            )
            if not existing:
                doc = {
                    **c,
                    "tenantId": tenant_id,
                    "membership": "Por registrar",
                    "membershipStatus": "NONE",
                    "isSeed": True,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow(),
                }
                await self.db.clients.insert_one(doc)
            client_map[c["firstName"]] = i

        now = datetime.utcnow()
        attendance_data = [
            {"firstName": "Juan", "name": "Juan Pérez", "checkIn": now - timedelta(hours=3), "checkOut": None, "date": now.strftime("%Y-%m-%d")},
            {"firstName": "Juan", "name": "Juan Pérez", "checkIn": now - timedelta(days=1, hours=4), "checkOut": now - timedelta(days=1, hours=1), "date": (now - timedelta(days=1)).strftime("%Y-%m-%d")},
            {"firstName": "María", "name": "María García", "checkIn": now - timedelta(hours=1), "checkOut": None, "date": now.strftime("%Y-%m-%d")},
            {"firstName": "Carlos", "name": "Carlos López", "checkIn": now - timedelta(days=1, hours=5), "checkOut": now - timedelta(days=1, hours=2), "date": (now - timedelta(days=1)).strftime("%Y-%m-%d")},
            {"firstName": "Ana", "name": "Ana Martínez", "checkIn": now - timedelta(days=2, hours=6), "checkOut": now - timedelta(days=2, hours=3), "date": (now - timedelta(days=2)).strftime("%Y-%m-%d")},
        ]

        for att in attendance_data:
            doc = {
                "clientId": client_map.get(att["firstName"], 0),
                "clientName": att["name"],
                "checkIn": att["checkIn"],
                "checkOut": att["checkOut"],
                "date": att["date"],
                "tenantId": tenant_id,
                "isSeed": True,
            }
            await self.db.attendance.insert_one(doc)

    async def seed_owner(self, tenant_id: str, email: str, business_name: str) -> None:
        """Crea el empleado owner y el usuario de login para un tenant demo.
        Idempotente: si ya existe un owner para este tenant, no hace nada.
        """
        # Verificar si ya existe un owner en employees
        existing_owner = await self.db.employees.find_one({
            "tenantId": tenant_id,
            "isOwner": True,
        })
        if existing_owner:
            if not existing_owner.get("isSeed"):
                await self.db.employees.update_one(
                    {"_id": existing_owner["_id"]},
                    {"$set": {"isSeed": True}},
                )

            existing_user = await self.db.users.find_one({
                "tenantId": tenant_id,
                "isOwner": True,
            })
            if existing_user:
                if not existing_user.get("isSeed"):
                    await self.db.users.update_one(
                        {"_id": existing_user["_id"]},
                        {"$set": {"isSeed": True}},
                    )
                return

            owner_id = str(existing_owner["_id"])
        else:
            owner_data = {
                "tenantId": tenant_id,
                "username": email,
                "documentType": "CEDULA",
                "documentNumber": "",
                "firstName": business_name,
                "lastName": "",
                "email": email,
                "phone": "",
                "role": "GERENTE",
                "status": "ACTIVE",
                "isOwner": True,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            result = await self.db.employees.insert_one(owner_data)
            owner_id = str(result.inserted_id)

        existing_user = await self.db.users.find_one({
            "username": email,
            "tenantId": tenant_id,
        })
        if not existing_user:
            from app.auth.utils import get_password_hash
            await self.db.users.insert_one({
                "username": email.lower(),
                "password_hash": get_password_hash("demo123456"),
                "role": "GERENTE",
                "employeeId": owner_id,
                "tenantId": tenant_id,
                "isOwner": True,
                "isSeed": True,
                "createdAt": datetime.utcnow(),
            })

    async def cleanup(self, tenant_id: str) -> dict:
        """Limpia todos los datos creados por un tenant demo.

        Elimina datos NO semilla (isSeed != True) de: Sales, Clients, Invoices,
        Products, Attendance, Services, Employees, Users, Notification configs/logs,
        Fingerprints.
        Mantiene: Tenant, servicios/empleados/usuarios seed.

        Retorna dict con mensaje y conteo de eliminados.
        """
        # Colecciones a limpiar (datos creados por el usuario, NO seed data)
        collections_to_clean = [
            Collections.SALES,
            Collections.CLIENTS,
            Collections.INVOICES,
            Collections.PRODUCTS,
            Collections.ATTENDANCE,
            Collections.SERVICES,
            Collections.EMPLOYEES,
            Collections.NOTIFICATION_CONFIGS,
            Collections.NOTIFICATION_LOGS,
            Collections.FINGERPRINTS,
        ]

        deleted_counts = {}
        for collection_name in collections_to_clean:
            result = await self.db[collection_name].delete_many({
                "tenantId": tenant_id,
                "isSeed": {"$ne": True},
            })
            deleted_counts[collection_name] = result.deleted_count

        # Limpiar usuarios creados por empleados demo (excluyendo seed)
        user_result = await self.db["users"].delete_many({
            "tenantId": tenant_id,
            "isSeed": {"$ne": True},
        })
        deleted_counts["users"] = user_result.deleted_count

        return {
            "message": "Datos demo eliminados correctamente",
            "deleted": deleted_counts,
            "tenantId": tenant_id,
        }


# ── Backward-compatible wrapper ─────────────────────────────────────────────


async def initialize_tenant_demo():
    """Top-level wrapper for calls from main.py (startup lifecycle).

    Import from app.services.tenant_demo:
        from app.services.tenant_demo import initialize_tenant_demo
    """
    from app.database import get_database
    service = TenantDemoService(get_database())
    return await service.initialize()
