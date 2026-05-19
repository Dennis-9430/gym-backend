#!/usr/bin/env python
"""Script CLI para gestionar credenciales del SUPER_ADMIN sin reiniciar el servidor.

Uso:
    python scripts/manage_super_admin.py --email admin@ejemplo.com --password nueva-pass
    python scripts/manage_super_admin.py --email admin@ejemplo.com
    python scripts/manage_super_admin.py --password nueva-pass
    python scripts/manage_super_admin.py --show

Flags:
    --email      Nuevo email del SUPER_ADMIN (opcional, si se omite mantiene el actual)
    --password   Nueva contraseña (opcional, si se omite mantiene la actual)
    --show       Muestra el email actual del SUPER_ADMIN (no revela la contraseña)
    --help       Muestra esta ayuda

Sin flags: muestra el email actual.

Requiere que el servidor NO esté corriendo (usa su propia conexión MongoDB).
"""
import argparse
import sys
import os

# Agregar backend/ al path para poder importar la app
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Gestionar credenciales del SUPER_ADMIN")
    parser.add_argument("--email", help="Nuevo email del SUPER_ADMIN")
    parser.add_argument("--password", help="Nueva contraseña del SUPER_ADMIN")
    parser.add_argument("--show", action="store_true", help="Mostrar email actual")
    args = parser.parse_args()

    if not args.email and not args.password and not args.show:
        parser.print_help()
        sys.exit(0)

    import asyncio
    asyncio.run(_run(args))


async def _run(args):
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.config import settings
    from app.auth.utils import get_password_hash

    # Conectar a MongoDB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    users_collection = db["users"]

    # Buscar SUPER_ADMIN actual (cualquier usuario con role=SUPER_ADMIN)
    current = await users_collection.find_one({"role": "SUPER_ADMIN"})

    if args.show:
        if current:
            print(f"Email actual: {current['username']}")
        else:
            print("No hay SUPER_ADMIN configurado.")
        client.close()
        return

    if not current:
        # Crear desde cero
        email = args.email or input("Email del SUPER_ADMIN: ").strip()
        password = args.password or input("Contraseña: ").strip()
        if not email or not password:
            print("ERROR: Email y contraseña son requeridos para crear un SUPER_ADMIN.")
            client.close()
            sys.exit(1)

        await users_collection.insert_one({
            "username": email.strip().lower(),
            "password_hash": get_password_hash(password),
            "role": "SUPER_ADMIN",
            "tenantId": None,
            "isOwner": False,
        })
        print(f"✅ SUPER_ADMIN creado: {email.strip().lower()}")
        client.close()
        return

    # Actualizar existente
    update_fields = {}
    if args.email:
        update_fields["username"] = args.email.strip().lower()
    if args.password:
        update_fields["password_hash"] = get_password_hash(args.password)

    if not update_fields:
        print("Sin cambios que aplicar.")
        client.close()
        return

    await users_collection.update_one(
        {"_id": current["_id"]},
        {"$set": update_fields},
    )

    changes = []
    if args.email:
        changes.append(f"email: {current['username']} → {args.email.strip().lower()}")
    if args.password:
        changes.append("contraseña: actualizada")

    print(f"✅ SUPER_ADMIN actualizado: {', '.join(changes)}")
    client.close()


if __name__ == "__main__":
    main()
