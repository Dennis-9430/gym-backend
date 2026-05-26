"""Check and fix passwords"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
from app.database import connect_to_mongodb, get_database, close_mongodb_connection
from app.auth.utils import verify_password, get_password_hash


async def main():
    await connect_to_mongodb()
    db = get_database()
    
    password = "demo123456"
    
    # Check demo-basic tenant password
    basic = await db.tenants.find_one({"businessCode": "demo-basic"})
    if basic and "password" in basic:
        ok = verify_password(password, basic["password"])
        print(f"Demo Basic tenant password matches 'demo123456': {ok}")
    
    # Check demo-pro tenant password  
    pro = await db.tenants.find_one({"businessCode": "demo-premium"})
    if pro and "password" in pro:
        ok = verify_password(password, pro["password"])
        print(f"Demo Pro tenant password matches 'demo123456': {ok}")
        if not ok:
            print("Fixing demo-pro tenant password...")
            await db.tenants.update_one(
                {"_id": pro["_id"]},
                {"$set": {"password": get_password_hash(password)}}
            )
            print("Fixed!")
    
    # Check demo-pro user password
    pro_user = await db.users.find_one({"username": "demo-pro@gmail.com"})
    if pro_user:
        ok = verify_password(password, pro_user["password_hash"])
        print(f"Demo Pro user password matches 'demo123456': {ok}")
        if not ok:
            print("Fixing demo-pro user password...")
            await db.users.update_one(
                {"_id": pro_user["_id"]},
                {"$set": {"password_hash": get_password_hash(password)}}
            )
            print("Fixed!")
    
    await close_mongodb_connection()


asyncio.run(main())
