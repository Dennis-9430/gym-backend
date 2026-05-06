"""
Script para insertar facturas de demo en MongoDB
Uso: python -m scripts.seed_invoices
"""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta
from bson import ObjectId
from app.database import get_database, Collections


def seed_invoices():
    db = get_database()
    
    # Obtener todos los tenants existentes
    tenants = list(db[Collections.TENANTS].find({}))
    
    if not tenants:
        print("No se encontraron tenants en la base de datos.")
        return
    
    print(f"Encontrados {len(tenants)} tenants:")
    for t in tenants:
        print(f"  - {t.get('businessName', 'Sin nombre')}: {t.get('tenantId')}")
    
    for tenant in tenants:
        tenant_id = tenant.get("tenantId")
        existing_count = db[Collections.INVOICES].count_documents({"tenantId": tenant_id})
        if existing_count > 0:
            print(f"Tenant {tenant_id} ya tiene {existing_count} facturas. Omitiendo...")
            continue
        
        # Crear 2 facturas de demo por tenant
        business_name = tenant.get("businessName", "Gimnasio")
        business_ruc = tenant.get("businessRuc", "")
        business_address = tenant.get("businessAddress", "")
        business_phone = tenant.get("businessPhone", "")
        business_email = tenant.get("email", "")
        
        invoices = [
            {
                "tenantId": tenant_id,
                "createdBy": tenant.get("ownerUsername", "Sistema"),
                "type": "MEMBERSHIP",
                "invoiceNumber": f"FAC-{datetime.now().year}-000001",
                "business": {
                    "name": business_name,
                    "ruc": business_ruc,
                    "address": business_address,
                    "phone": business_phone,
                    "email": business_email
                },
                "client": {
                    "documentNumber": "1723456789",
                    "firstName": "Andrés",
                    "lastName": "Pinzón",
                    "email": "andres.pinzon@email.com"
                },
                "items": [
                    {"name": "Membresía Mensual", "quantity": 1, "unitPrice": 29.5, "unitDiscount": 0, "subtotal": 29.5}
                ],
                "totals": {
                    "subtotal": 29.5,
                    "discountAmount": 0,
                    "taxAmount": 3.54,
                    "iceAmount": 0,
                    "total": 33.04
                },
                "payment": {
                    "method": "CASH",
                    "cashAmount": 33.04,
                    "transferAmount": 0,
                    "paid": 33.04,
                    "change": 0
                },
                "status": "GENERATED",
                "createdAt": datetime.utcnow() - timedelta(days=2)
            },
            {
                "tenantId": tenant_id,
                "createdBy": tenant.get("ownerUsername", "Sistema"),
                "type": "MEMBERSHIP",
                "invoiceNumber": f"FAC-{datetime.now().year}-000002",
                "business": {
                    "name": business_name,
                    "ruc": business_ruc,
                    "address": business_address,
                    "phone": business_phone,
                    "email": business_email
                },
                "client": {
                    "documentNumber": "0103456789",
                    "firstName": "María",
                    "lastName": "García",
                    "email": "maria.garcia@email.com"
                },
                "items": [
                    {"name": "Paquete 10 Clases", "quantity": 10, "unitPrice": 8, "unitDiscount": 0, "subtotal": 80}
                ],
                "totals": {
                    "subtotal": 80,
                    "discountAmount": 0,
                    "taxAmount": 9.6,
                    "iceAmount": 0,
                    "total": 89.6
                },
                "payment": {
                    "method": "TRANSFER",
                    "cashAmount": 0,
                    "transferAmount": 89.6,
                    "paid": 89.6,
                    "change": 0
                },
                "status": "SENT",
                "createdAt": datetime.utcnow() - timedelta(days=5)
            }
        ]
        
        # Actualizar contadores
        db.counters.update_one(
            {"tenantId": tenant_id},
            {"$set": {"invoiceCount": 2}},
            upsert=True
        )
        
        # Insertar facturas
        result = db[Collections.INVOICES].insert_many(invoices)
        print(f"Tenant {tenant_id}: Insertadas {len(result.inserted_ids)} facturas de demo")
        
    print("\nFacturas de demo insertadas correctamente!")
    
    # Mostrar resumen
    for tenant in tenants:
        tenant_id = tenant.get("tenantId")
        count = db[Collections.INVOICES].count_documents({"tenantId": tenant_id})
        print(f"  {tenant.get('businessName')}: {count} facturas")

if __name__ == "__main__":
    print("Insertando facturas de demo en MongoDB...")
    seed_invoices()
