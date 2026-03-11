"""
Create demo tenant and 5 users with different roles via API.

- Tenant: subdomain=demo, domain=127.0.0.1
- User 1: demo@moio.ai (tenant_admin) - creado por self-provision
- User 2: admin2@demo.moio.ai (tenant_admin)
- User 3: manager@demo.moio.ai (manager)
- User 4: member@demo.moio.ai (member)
- User 5: member2@demo.moio.ai (member)
- User 6: member3@demo.moio.ai (member)
- User 7: viewer@demo.moio.ai (viewer)

Prerequisites: backend running (DB migrated).

Usage:
  cd backend && python tests/demo/setup_demo_tenant.py
  BASE_URL=http://127.0.0.1:8093 python tests/demo/setup_demo_tenant.py
"""
from __future__ import annotations

import os
import sys

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8093").rstrip("/")
HOST = "demo.127.0.0.1"
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@moio.ai")
DEMO_PASS = os.environ.get("DEMO_PASS", "demo123")

USERS = [
    {"email": "admin2@demo.moio.ai", "password": "admin2123", "first_name": "Admin", "last_name": "Dos", "role": "tenant_admin"},
    {"email": "manager@demo.moio.ai", "password": "manager123", "first_name": "Manager", "last_name": "Demo", "role": "manager"},
    {"email": "member@demo.moio.ai", "password": "member123", "first_name": "Member", "last_name": "Demo", "role": "member"},
    {"email": "member2@demo.moio.ai", "password": "member2123", "first_name": "Member", "last_name": "Dos", "role": "member"},
    {"email": "member3@demo.moio.ai", "password": "member3123", "first_name": "Member", "last_name": "Tres", "role": "member"},
    {"email": "viewer@demo.moio.ai", "password": "viewer123", "first_name": "Viewer", "last_name": "Demo", "role": "viewer"},
]


def main() -> int:
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"

    token = None

    # 1. Try self-provision (creates tenant + first user)
    print("Creating tenant (self-provision)...")
    prov = session.post(
        f"{BASE_URL}/api/v1/tenants/self-provision/",
        params={"sync": "1"},
        json={
            "nombre": "Demo",
            "subdomain": "demo",
            "domain": "127.0.0.1",
            "plan": "pro",  # pro/business enable users_manage for tenant_admin
            "email": DEMO_EMAIL,
            "username": DEMO_EMAIL,
            "password": DEMO_PASS,
            "first_name": "Demo",
            "last_name": "Admin",
        },
    )

    if prov.status_code == 201:
        data = prov.json()
        token = data.get("access_token") or data.get("access")
        print(f"  Tenant created. User: {DEMO_EMAIL}")
    elif prov.status_code in (400, 409):
        err = prov.json() if prov.headers.get("content-type", "").startswith("application/json") else {}
        msg = err.get("subdomain") or err.get("email") or err.get("detail") or prov.text
        if "already" in str(msg).lower() or "taken" in str(msg).lower() or "registered" in str(msg).lower():
            print("  Tenant/subdomain already exists. Logging in...")
            login = session.post(
                f"{BASE_URL}/api/v1/auth/login/",
                json={"email": DEMO_EMAIL, "password": DEMO_PASS},
            )
            if login.status_code != 200:
                print(f"  Login failed: {login.status_code} {login.text[:200]}")
                return 1
            token = login.json().get("access")
        else:
            print(f"  Provision failed: {msg}")
            return 1
    else:
        print(f"  Provision failed: {prov.status_code} {prov.text[:300]}")
        return 1

    if not token:
        print("  No token obtained.")
        return 1

    session.headers["Authorization"] = f"Bearer {token}"
    session.headers["Host"] = HOST

    # 2. Create 6 additional users
    print("Creating users...")
    created = 0
    for u in USERS:
        resp = session.post(
            f"{BASE_URL}/api/v1/users/",
            json={
                "email": u["email"],
                "username": u["email"],
                "password": u["password"],
                "first_name": u["first_name"],
                "last_name": u["last_name"],
                "role": u["role"],
            },
        )
        if resp.status_code in (200, 201):
            created += 1
            print(f"  {u['email']} ({u['role']})")
        else:
            err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if "already" in str(err).lower():
                print(f"  {u['email']} - already exists")
            else:
                print(f"  {u['email']} failed: {resp.status_code} {resp.text[:150]}")

    print(f"\nDone. Tenant demo, 7 users (1 from provision + {created} created).")
    print("Credentials:")
    print(f"  {DEMO_EMAIL} / {DEMO_PASS} (tenant_admin)")
    for u in USERS:
        print(f"  {u['email']} / {u['password']} ({u['role']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
