"""Detailed check of demo-premium tenant"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    tenant = await db.tenants.find_one({"businessCode": "demo-premium"})
    if not tenant:
        print("demo-premium NOT found")
        return
    
    print("=== Demo Premium TENANT (full dump) ===")
import json
from datetime import datetime
from bson import ObjectId
    
    class MongoEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, ObjectId):
                return str(obj)
            if isinstance(obj, datetime):
                return obj.isoformat()
            return super().default(obj)
    
    print(json.dumps(tenant, indent=2, cls=MongoEncoder))
    
    print("\n=== Keys ===")
    for k, v in tenant.items():
        if k == "_id":
            continue
        print(f"  {k}: {v}")
    
    print("\n=== Demo Basic tenant (for comparison) ===")
    basic = await db.tenants.find_one({"businessCode": "demo-basic"})
    if basic:
        print(f"  plan: {basic.get('plan')}")
        print(f"  isDemo: {basic.get('isDemo')}")
        print(f"  has password: {'password' in basic}")
    
    await close_mongodb_connection()


asyncio.run(main())
