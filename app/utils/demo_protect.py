# Utilidad para proteger datos seed en cuentas demo
# Relacionado con: routers/products.py, clients.py, sales.py, services.py
"""Demo seed data protection utilities"""
from fastapi import HTTPException, status
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import Collections


async def check_seed_protected(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    collection: str,
    doc_id: str,
    action: str = "modificar"
):
    """Verifica si un documento es seed data de un tenant demo y rechaza la operación.
    
    Args:
        db: Base de datos
        tenant_id: ID del tenant
        collection: Nombre de la colección (ej: Collections.PRODUCTS)
        doc_id: ObjectId del documento como string
        action: Nombre de la acción para el mensaje de error (ej: "modificar", "eliminar")
    
    Raises:
        HTTPException 403 si el tenant es demo y el documento es seed
    """
    if not ObjectId.is_valid(doc_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID inválido"
        )
    
    # Verificar si el tenant es demo
    tenant = await db[Collections.TENANTS].find_one({"tenantId": tenant_id})
    if not tenant or not tenant.get("isDemo"):
        return  # No es demo, permitir operación
    
    # Verificar si el documento es seed
    doc = await db[collection].find_one({"_id": ObjectId(doc_id)})
    if doc and doc.get("isSeed"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Los datos de demostración no pueden ser {action}."
        )
