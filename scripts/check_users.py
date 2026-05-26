"""Check demo users"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    # Check demo-basic user
    basic_user = await db.users.find_one({"username": "demo-basic@gmail.com"})
    if basic_user:
        print("=== Demo Basic user ===")
        print(f"  role: {basic_user.get('role')}")
        print(f"  tenantId: {basic_user.get('tenantId')}")
        print(f"  employeeId: {basic_user.get('employeeId')}")
        print(f"  isOwner: {basic_user.get('isOwner')}")
    else:
        print("Demo Basic user NOT found in 'users'")
    
    # Check demo-pro user (just created)
    pro_user = await db.users.find_one({"username": "demo-pro@gmail.com"})
    if pro_user:
        print()
        print("=== Demo Pro user ===")
        print(f"  role: {pro_user.get('role')}")
        print(f"  tenantId: {pro_user.get('tenantId')}")
        print(f"  employeeId: {pro_user.get('employeeId')}")
        print(f"  isOwner: {pro_user.get('isOwner')}")
    else:
        print("Demo Pro user NOT found in 'users'")
    
    # Check tenant passwords
    print()
    print("=== Tenant passwords ===")
    basic_tenant = await db.tenants.find_one({"businessCode": "demo-basic"})
    pro_tenant = await db.tenants.find_one({"businessCode": "demo-premium"})
    
    if basic_tenant and "password" in basic_tenant:
        print(f"Demo Basic: has password = True")
    if pro_tenant and "password" in pro_tenant:
        print(f"Demo Pro: has password = True")
    
    await close_mongodb_connection()


asyncio.run(main())
