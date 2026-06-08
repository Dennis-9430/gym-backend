"""Demo data cleanup router — thin controller delegating to TenantDemoService"""
from fastapi import APIRouter, Depends, HTTPException, status
from app.database import get_database, Collections
from app.auth.router import get_current_user
from app.auth.schemas import UserResponse
from app.services.tenant_demo import TenantDemoService

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

    service = TenantDemoService(db)
    result = await service.cleanup(current_user.tenantId)

    return {
        "message": result["message"],
        "deleted": result["deleted"],
        "tenantId": result["tenantId"],
    }
