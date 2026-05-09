"""
Script simple para insertar facturas de demo
Ejecuta esto mientras el backend está corriendo
"""
import pymongo
import os
from dotenv import load_dotenv
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("MONGODB_DB_NAME", "gym_db")

def seed_invoices():
    client = pymongo.MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    
    # Obtener tenants
    tenants = list(db.tenants.find({}))
    print(f"Encontrados {len(tenants)} tenants")
    
    for t in tenants:
        tid = t.get("tenantId")
        count = db.invoices.count_documents({"tenantId": tid})
        
        if count > 0:
            print(f"{t.get('businessName', tid)}: ya tiene {count} facturas")
            continue
        
        # Insertar factura
        inv = {
            "tenantId": tid,
            "createdBy": t.get("ownerUsername", "Sistema"),
            "type": "MEMBERSHIP",
            "invoiceNumber": "FAC-2025-000001",
            "business": {
                "name": t.get("businessName", "Gimnasio"),
                "ruc": t.get("businessRuc", ""),
                "address": t.get("businessAddress", ""),
                "phone": t.get("businessPhone", ""),
                "email": t.get("email", "")
            },
            "client": {
                "documentNumber": "1723456789",
                "firstName": "Andres",
                "lastName": "Pinzon",
                "email": "andres@email.com"
            },
            "items": [
                {"name": "Membresia Mensual", "quantity": 1, "unitPrice": 29.5, "unitDiscount": 0, "subtotal": 29.5}
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
            "status": "GENERATED"
        }
        
        db.invoices.insert_one(inv)
        db.counters.update_one(
            {"tenantId": tid},
            {"$set": {"invoiceCount": 1}},
            upsert=True
        )
        print(f"{t.get('businessName', tid)}: inserted 1 invoice")
    
    client.close()
    print("\nListo!")

if __name__ == "__main__":
    seed_invoices()
