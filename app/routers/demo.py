# Router para limpieza de datos demo
# Relacionado con: models/tenant.py, routers/tenants.py
"""Demo data cleanup router"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from app.database import get_database, Collections
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse

router = APIRouter(prefix="/api/tenants", tags=["demo"])


@router.post("/demo/cleanup")
async def cleanup_demo_data(current_user: UserResponse = Depends(get_current_user)):
    """Limpia todos los datos creados por un tenant demo.
    
    Elimina: Sales, Clients, Invoices, Products, Attendance
    Mantiene: Tenant, Services (seed), Employees (seed), Users (seed)
    Solo funciona para cuentas demo.
    """
    if not current_user.tenantId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant ID found"
        )
    
    db = get_database()
    
    # Verificar que sea un tenant demo
    tenant = await db[Collections.TENANTS].find_one(
        {"tenantId": current_user.tenantId}
    )
    if not tenant or not tenant.get("isDemo", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operación solo está disponible para cuentas demo"
        )
    
    tenant_id = current_user.tenantId
    
    # Colecciones a limpiar (datos creados por el usuario, NO seed data)
    # Excluye documentos con isSeed=true para preservar datos semilla
    collections_to_clean = [
        Collections.SALES,
        Collections.CLIENTS,
        Collections.INVOICES,
        Collections.PRODUCTS,
        Collections.ATTENDANCE,
    ]
    
    deleted_counts = {}
    for collection_name in collections_to_clean:
        # Solo borra datos NO semilla (isSeed != true)
        result = await db[collection_name].delete_many({
            "tenantId": tenant_id,
            "isSeed": {"$ne": True},
        })
        deleted_counts[collection_name] = result.deleted_count
    
    return {
        "message": "Datos demo eliminados correctamente",
        "deleted": deleted_counts,
        "tenantId": tenant_id,
    }
