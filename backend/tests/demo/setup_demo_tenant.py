"""
Create demo tenant and users with different roles via API.

- Tenant defaults: subdomain=demo, domain=127.0.0.1
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
  BASE_URL=https://moio.ai DEMO_HOST=demo.moio.ai DEMO_DOMAIN=moio.ai python tests/demo/setup_demo_tenant.py
"""
from __future__ import annotations

import os
import sys
import time

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8093").rstrip("/")
DEMO_SUBDOMAIN = os.environ.get("DEMO_SUBDOMAIN", "demo").strip() or "demo"
DEMO_DOMAIN = os.environ.get("DEMO_DOMAIN", "127.0.0.1").strip() or "127.0.0.1"
HOST = os.environ.get("DEMO_HOST", f"{DEMO_SUBDOMAIN}.{DEMO_DOMAIN}").strip() or f"{DEMO_SUBDOMAIN}.{DEMO_DOMAIN}"
DEMO_TENANT_NAME = os.environ.get("DEMO_TENANT_NAME", "Demo").strip() or "Demo"
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", f"{DEMO_SUBDOMAIN}@moio.ai").strip() or f"{DEMO_SUBDOMAIN}@moio.ai"
DEMO_PASS = os.environ.get("DEMO_PASS", f"{DEMO_SUBDOMAIN}123").strip() or f"{DEMO_SUBDOMAIN}123"


def _demo_users() -> list[dict[str, str]]:
    return [
        {"email": f"admin2@{DEMO_SUBDOMAIN}.moio.ai", "password": "admin2123", "first_name": "Admin", "last_name": "Dos", "role": "tenant_admin"},
        {"email": f"manager@{DEMO_SUBDOMAIN}.moio.ai", "password": "manager123", "first_name": "Manager", "last_name": DEMO_TENANT_NAME, "role": "manager"},
        {"email": f"member@{DEMO_SUBDOMAIN}.moio.ai", "password": "member123", "first_name": "Member", "last_name": DEMO_TENANT_NAME, "role": "member"},
        {"email": f"member2@{DEMO_SUBDOMAIN}.moio.ai", "password": "member2123", "first_name": "Member", "last_name": "Dos", "role": "member"},
        {"email": f"member3@{DEMO_SUBDOMAIN}.moio.ai", "password": "member3123", "first_name": "Member", "last_name": "Tres", "role": "member"},
        {"email": f"viewer@{DEMO_SUBDOMAIN}.moio.ai", "password": "viewer123", "first_name": "Viewer", "last_name": DEMO_TENANT_NAME, "role": "viewer"},
    ]


def main() -> int:
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"

    token = None

    # 1. Try self-provision (creates tenant + first user)
    print("Creating tenant (self-provision)...")
    prov = session.post(
        f"{BASE_URL}/api/v1/tenants/self-provision/",
        json={
            "nombre": DEMO_TENANT_NAME,
            "subdomain": DEMO_SUBDOMAIN,
            "domain": DEMO_DOMAIN,
            "email": DEMO_EMAIL,
            "username": DEMO_EMAIL,
            "password": DEMO_PASS,
            "first_name": "Demo",
            "last_name": "Admin",
        },
    )

    if prov.status_code == 202:
        data = prov.json()
        task_id = data.get("task_id")
        if not task_id:
            print(f"  Provision queued without task id: {prov.text[:300]}")
            return 1
        print(f"  Provision queued ({task_id}). Polling...")
        for _ in range(90):
            status_resp = session.get(f"{BASE_URL}/api/v1/tenants/provision-status/{task_id}/")
            payload = status_resp.json() if status_resp.headers.get("content-type", "").startswith("application/json") else {}
            state = payload.get("status")
            if state == "success":
                token = payload.get("access_token") or payload.get("access")
                print(f"  Tenant created. User: {DEMO_EMAIL}")
                break
            if state == "failure":
                print(f"  Provision failed: {payload.get('error') or status_resp.text[:300]}")
                return 1
            current_stage = payload.get("current_stage") or "pending"
            print(f"  Waiting... stage={current_stage} status={state}")
            time.sleep(2)
        else:
            print("  Provision timeout.")
            return 1
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
    users = _demo_users()
    for u in users:
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

    print(f"\nDone. Tenant {DEMO_SUBDOMAIN}, 7 users (1 from provision + {created} created).")
    print("Credentials:")
    print(f"  {DEMO_EMAIL} / {DEMO_PASS} (tenant_admin)")
    for u in users:
        print(f"  {u['email']} / {u['password']} ({u['role']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
