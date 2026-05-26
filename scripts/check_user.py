"""Check user login data"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection
from app.auth.utils import get_password_hash


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    email = "demo-pro@gmail.com"
    
    # Check users collection
    user = await db.users.find_one({"username": email})
    if user:
        print(f"User found in 'users':")
        print(f"  role: {user.get('role')}")
        print(f"  tenantId: {user.get('tenantId')}")
        if user.get("tenantId"):
            tenant = await db.tenants.find_one({"tenantId": user["tenantId"]})
            if tenant:
                print(f"  tenant: {tenant.get('businessName')} | plan: {tenant.get('plan')} | code: {tenant.get('businessCode')}")
    else:
        print(f"User '{email}' NOT found in 'users'")
    
    # Check employees collection
    emp = await db.employees.find_one({"email": email})
    if emp:
        print(f"\nEmployee found:")
        print(f"  tenantId: {emp.get('tenantId')}")
        print(f"  role: {emp.get('role')}")
        if emp.get("tenantId"):
            tenant = await db.tenants.find_one({"tenantId": emp["tenantId"]})
            if tenant:
                print(f"  tenant: {tenant.get('businessName')} | plan: {tenant.get('plan')} | code: {tenant.get('businessCode')}")
    else:
        print(f"Employee '{email}' NOT found")
    
    # Check all users with "demo" in username
    print("\nAll demo users:")
    demo_users = await db.users.find({"username": {"$regex": "demo", "$options": "i"}}).to_list(10)
    for u in demo_users:
        print(f"  - {u.get('username')} | role={u.get('role')} | tenantId={u.get('tenantId')}")
    
    # Check all employees with "demo" in email
    print("\nAll demo employees:")
    demo_emps = await db.employees.find({"email": {"$regex": "demo", "$options": "i"}}).to_list(10)
    for e in demo_emps:
        print(f"  - {e.get('email')} | role={e.get('role')} | tenantId={e.get('tenantId')}")
    
    # Check demo-premium tenant details
    print("\nDemo Premium tenant:")
    tenant = await db.tenants.find_one({"businessCode": "demo-premium"})
    if tenant:
        print(f"  businessName: {tenant.get('businessName')}")
        print(f"  plan: {tenant.get('plan')}")
        print(f"  tenantId: {tenant.get('tenantId')}")
        print(f"  ownerEmail: {tenant.get('email')}")
    
    await close_mongodb_connection()


asyncio.run(main())
