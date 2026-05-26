"""Simple tenant check"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    tenant = await db.tenants.find_one({"businessCode": "demo-premium"})
    if not tenant:
        print("demo-premium NOT found")
        return
    
    print("=== Demo Premium TENANT ===")
    for k, v in tenant.items():
        if k == "_id":
            print(f"  _id: {str(v)}")
        else:
            print(f"  {k}: {v}")
    
    print()
    print("=== Demo Basic for comparison ===")
    basic = await db.tenants.find_one({"businessCode": "demo-basic"})
    if basic:
        print(f"  plan: {basic.get('plan')}")
        print(f"  isDemo: {basic.get('isDemo')}")
        print(f"  has password: {'password' in basic}")
        print(f"  email: {basic.get('email')}")
    
    await close_mongodb_connection()


asyncio.run(main())
