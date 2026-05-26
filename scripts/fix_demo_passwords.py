"""Fix both demo tenant passwords to match demo123456"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection
from app.auth.utils import get_password_hash


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    password = "demo123456"
    hashed = get_password_hash(password)
    
    # Fix demo-basic tenant password
    basic = await db.tenants.find_one({"businessCode": "demo-basic"})
    if basic:
        await db.tenants.update_one(
            {"_id": basic["_id"]},
            {"$set": {"password": hashed}}
        )
        print("Demo Basic tenant password updated to demo123456")
    
    # Fix demo-basic user in users collection if it exists
    basic_user = await db.users.find_one({"username": "demo-basic@gmail.com"})
    if basic_user:
        await db.users.update_one(
            {"_id": basic_user["_id"]},
            {"$set": {"password_hash": hashed}}
        )
        print("Demo Basic user password updated")
    else:
        # Create the user if not exists
        emp = await db.employees.find_one({"email": "demo-basic@gmail.com"})
        if emp:
            await db.users.insert_one({
                "username": "demo-basic@gmail.com",
                "password_hash": hashed,
                "role": "ADMIN",
                "tenantId": emp["tenantId"],
                "employeeId": str(emp["_id"]),
                "isOwner": True,
            })
            print("Demo Basic user CREATED in users collection")
    
    # Verify demo-pro is still correct
    pro_user = await db.users.find_one({"username": "demo-pro@gmail.com"})
    if pro_user:
        print("Demo Pro user: OK")
    
    pro_tenant = await db.tenants.find_one({"businessCode": "demo-premium"})
    if pro_tenant:
        print("Demo Pro tenant: OK")
    
    await close_mongodb_connection()


asyncio.run(main())
