import argparse
import getpass
import ipaddress
import os
import sys
from pathlib import Path

import uvicorn

from .config import Settings
from .db import backup, connect, initialize
from .demo import DEMO_PASSWORD, DEMO_USERS, seed_demo
from .security import digest_token, hash_password, normalize_email


def set_user(settings, args):
    email = normalize_email(args.email)
    name = args.name.strip()
    if not 2 <= len(name) <= 100:
        raise ValueError("Provide a display name between 2 and 100 characters.")
    password = getpass.getpass("Password (at least 15 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation or not 15 <= len(password) <= 128:
        raise ValueError("Passwords must match and contain 15 to 128 characters.")
    if password == DEMO_PASSWORD:
        raise ValueError("Choose a unique password.")
    hashed = hash_password(password)
    with connect(settings.database, write=True) as connection:
        row = connection.execute("SELECT id, role FROM users WHERE email = ?", (email,)).fetchone()
        if row and not args.update:
            raise ValueError("The account already exists. Pass --update to rotate its password or role.")
        if row:
            if args.role != row["role"] and connection.execute(
                """SELECT 1 FROM events WHERE owner_id = ?
                UNION ALL SELECT 1 FROM registrations WHERE student_id = ? LIMIT 1""",
                (row["id"], row["id"]),
            ).fetchone():
                raise ValueError("This account has event history. Provision a separate account for the new role.")
            connection.execute("UPDATE users SET name = ?, role = ?, password_hash = ?, active = 1 WHERE id = ?",
                               (name, args.role, hashed, row["id"]))
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            connection.execute("DELETE FROM login_attempts WHERE scope = ?", (f"account:{digest_token(email)}",))
        else:
            connection.execute("INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                               (email, name, hashed, args.role))
    print(f"Account provisioned for {email}.")


def deactivate_user(settings, args):
    email = normalize_email(args.email)
    with connect(settings.database, write=True) as connection:
        user = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            raise ValueError("Account not found.")
        connection.execute("UPDATE users SET active = 0 WHERE id = ?", (user["id"],))
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    print(f"Account deactivated for {email}.")


def main():
    parser = argparse.ArgumentParser(description="CampusLoop campus event portal")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    commands.add_parser("init")
    commands.add_parser("seed-demo")
    user = commands.add_parser("user")
    user.add_argument("email")
    user.add_argument("name")
    user.add_argument("role", choices=["student", "organizer"])
    user.add_argument("--update", action="store_true")
    deactivate = commands.add_parser("deactivate")
    deactivate.add_argument("email")
    copy = commands.add_parser("backup")
    copy.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        if args.command == "serve":
            trusted_proxy = os.environ.get("CAMPUSLOOP_TRUSTED_PROXY")
            if trusted_proxy:
                ipaddress.ip_address(trusted_proxy)
            uvicorn.run("campusloop.app:create_app", factory=True, host=args.host, port=args.port,
                        proxy_headers=bool(trusted_proxy), forwarded_allow_ips=trusted_proxy,
                        limit_concurrency=100)
            return
        initialize(settings.database)
        if args.command == "seed-demo":
            seed_demo(settings)
            print("Local review accounts:")
            for email, _, role in DEMO_USERS:
                print(f"  {role}: {email}")
            print(f"  password: {DEMO_PASSWORD}")
        elif args.command == "user":
            set_user(settings, args)
        elif args.command == "deactivate":
            deactivate_user(settings, args)
        elif args.command == "backup":
            backup(settings.database, args.destination.resolve())
            print(f"Backup saved to {args.destination.resolve()}.")
        else:
            print(f"Database ready at {settings.database}.")
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    sys.exit(main())
