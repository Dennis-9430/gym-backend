"""Check demo-pro tenant in MongoDB"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    # Buscar por businessCode exacto
    tenant = await db.tenants.find_one({"businessCode": "demo-pro"})
    if tenant:
        print("Found demo-pro:")
        print(f"  businessName: {tenant.get('businessName')}")
        print(f"  plan: {tenant.get('plan')}")
        print(f"  tenantId: {tenant.get('tenantId')}")
        print(f"  businessCode: {tenant.get('businessCode')}")
        print(f"  subscriptionStatus: {tenant.get('subscriptionStatus')}")
    else:
        print("demo-pro NOT found by businessCode")
        # Buscar otros tenants
        tenants = await db.tenants.find({}).to_list(20)
        print(f"\nAll tenants ({len(tenants)}):")
        for t in tenants:
            print(f"  - {t.get('businessName')} | code={t.get('businessCode')} | plan={t.get('plan')} | status={t.get('subscriptionStatus')}")
    
    await close_mongodb_connection()


asyncio.run(main())
