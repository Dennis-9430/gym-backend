"""Create missing user record for demo-pro@gmail.com"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection
from app.auth.utils import get_password_hash


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    email = "demo-pro@gmail.com"
    password = "demo123456"
    
    # Check if user already exists
    existing = await db.users.find_one({"username": email})
    if existing:
        print(f"User {email} already exists with role={existing.get('role')}, tenantId={existing.get('tenantId')}")
        return
    
    # Get the employee to find tenantId
    emp = await db.employees.find_one({"email": email})
    if not emp:
        print(f"Employee {email} not found")
        return
    
    tenant_id = emp["tenantId"]
    tenant = await db.tenants.find_one({"tenantId": tenant_id})
    tenant_name = tenant.get("businessName", "Unknown") if tenant else "Unknown"
    
    # Create user
    user_doc = {
        "username": email,
        "password_hash": get_password_hash(password),
        "role": "ADMIN",
        "tenantId": tenant_id,
        "employeeId": str(emp.get("_id")),
        "isOwner": True,
        "createdAt": emp.get("createdAt"),
    }
    
    result = await db.users.insert_one(user_doc)
    print(f"✅ Created user for {email}")
    print(f"  tenant: {tenant_name} ({tenant_id})")
    print(f"  role: ADMIN (owner)")
    print(f"  password: {password}")
    
    await close_mongodb_connection()


asyncio.run(main())
