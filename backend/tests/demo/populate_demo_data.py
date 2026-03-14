"""
Populate demo tenant with 50 companies, 250 contacts, and 500 activities via the HTTP API.
Uses multiple users (alternating) and async/concurrent requests to simulate real-life
usage with potential clashing and concurrency.

Prerequisites:
  1. Tenant demo + users: python tests/demo/setup_demo_tenant.py
  2. Backend running (e.g. hypercorn -c file:hypercorn_dev.py moio_platform.asgi:application)

Usage:
  cd backend && python tests/demo/populate_demo_data.py
  BASE_URL=http://127.0.0.1:8093 DEMO_SLUG=demo python tests/demo/populate_demo_data.py
  BASE_URL=https://moio.ai DEMO_SLUG=demostracion DEMO_HOST=demostracion.moio.ai python tests/demo/populate_demo_data.py

Env:
  DEMO_SLUG: tenant/data namespace (default demo)
  DEMO_HOST: tenant host header (default <slug>.<domain>)
  DEMO_DOMAIN: base domain for DEMO_HOST defaults (default 127.0.0.1)
  DEMO_ADMIN_EMAIL: primary login user (default <slug>@moio.ai)
  DEMO_ADMIN_PASS: primary login password (default <slug>123)
  POPULATE_CONCURRENCY: max concurrent requests (default 8)
  POPULATE_DELAY_MS: min delay between batches, ms (default 50)
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import timedelta
from typing import Any

try:
    import httpx
except ImportError:
    print("pip install httpx")
    sys.exit(1)

DEMO_SLUG = os.environ.get("DEMO_SLUG", "demo").strip() or "demo"
DEMO_DOMAIN = os.environ.get("DEMO_DOMAIN", "127.0.0.1").strip() or "127.0.0.1"
DEMO_HOST = os.environ.get("DEMO_HOST", f"{DEMO_SLUG}.{DEMO_DOMAIN}").strip() or f"{DEMO_SLUG}.{DEMO_DOMAIN}"
DEMO_ADMIN_EMAIL = os.environ.get("DEMO_ADMIN_EMAIL", f"{DEMO_SLUG}@moio.ai").strip() or f"{DEMO_SLUG}@moio.ai"
DEMO_ADMIN_PASS = os.environ.get("DEMO_ADMIN_PASS", f"{DEMO_SLUG}123").strip() or f"{DEMO_SLUG}123"
DEMO_CONTACT_EMAIL_DOMAIN = (
    os.environ.get("DEMO_CONTACT_EMAIL_DOMAIN", f"{DEMO_SLUG}.example.com").strip() or f"{DEMO_SLUG}.example.com"
)


def _demo_users() -> list[tuple[str, str]]:
    return [
        (DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASS),
        (f"admin2@{DEMO_SLUG}.moio.ai", "admin2123"),
        (f"manager@{DEMO_SLUG}.moio.ai", "manager123"),
        (f"member@{DEMO_SLUG}.moio.ai", "member123"),
        (f"member2@{DEMO_SLUG}.moio.ai", "member2123"),
        (f"member3@{DEMO_SLUG}.moio.ai", "member3123"),
        (f"viewer@{DEMO_SLUG}.moio.ai", "viewer123"),  # viewer may get 403 on creates - realistic
    ]

COMPANY_NAMES = [
    "Tienda Inglesa", "Ta-Ta", "Geant", "Devoto", "Disco",
    "Carrefour", "Supermercados Toledo", "Bigbox", "Multiahorro",
    "Mercado Libre Uruguay", "PedidosYa", "Globant Uruguay", "dLocal",
    "Genexus", "K2B", "Abstracta", "Tryolabs", "Rootstrap",
    "Gearbox Software", "InSwitch", "Infocorp", "Banco Itaú",
    "Santander Uruguay", "BROU", "Antel", "Movistar Uruguay",
    "UTE", "OSE", "ANCAP", "Puertos del Estado",
    "Zonamerica", "Campus Party", "UTEC", "Universidad ORT",
    "Curtice Burns", "Conaprole", "Frigorífico Tacuarembó",
    "Pablo Atchugarry", "Teatro Solís", "Museo Torres García",
    "Hotel Sofitel", "Radisson Victoria Plaza", "Hyatt Centric",
    "Restaurant García", "La Perdiz", "Maroñas Mall",
    "Acme Corp", "TechSolutions SA", "Consultora Delta", "Startup Labs",
    "Importadora Oriental", "Logística Express", "Ferretería Central",
]

FIRST_NAMES = [
    "Ana", "Carlos", "María", "Pedro", "Laura", "Diego", "Valentina", "Roberto",
    "Lucía", "Andrés", "Fernanda", "Miguel", "Patricia", "Ricardo", "Camila",
    "Juan", "Sofía", "Martín", "Isabel", "José", "Elena", "Francisco", "Carmen",
]

LAST_NAMES = [
    "González", "Rodríguez", "Martínez", "Fernández", "López", "Pérez", "García",
    "Silva", "Costa", "Méndez", "Suárez", "Ramos", "Moreno", "Díaz", "Álvarez",
]

ACTIVITY_TITLES = [
    "Llamada de seguimiento", "Reunión de ventas", "Envío de propuesta",
    "Nota de reunión", "Tarea: enviar documentación", "Llamada inicial",
    "Demo de producto", "Negociación de contrato", "Seguimiento post-reunión",
    "Presentación ejecutiva", "Revisión de oferta", "Consulta técnica",
    "Visita a oficina", "Almuerzo de negocios", "Webinar de capacitación",
    "Seguimiento por email", "Llamada de cierre", "Reunión de kick-off",
    "Revisión de SLA", "Renegociación", "Onboarding cliente",
]


def _random_iso_in_last_90_days() -> str:
    from datetime import timezone as tz
    from datetime import datetime

    delta = timedelta(days=random.randint(0, 90))
    dt = datetime.now(tz.utc) - delta
    return dt.isoformat().replace("+00:00", "Z")


async def _login_user(client: httpx.AsyncClient, base: str, email: str, password: str) -> str | None:
    resp = await client.post(
        f"{base}/api/v1/auth/login/",
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get("access")


async def run(
    base_url: str,
    host: str,
    n_companies: int = 50,
    n_contacts: int = 250,
    n_activities: int = 500,
    concurrency: int = 8,
    delay_ms: float = 50,
) -> int:
    base = base_url.rstrip("/")
    delay = delay_ms / 1000.0
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=30.0) as client:
        client.headers["Content-Type"] = "application/json"

        # 1. Login all users
        print("Logging in users...")
        tokens: list[str | None] = []
        demo_users = _demo_users()
        for email, password in demo_users:
            tok = await _login_user(client, base, email, password)
            tokens.append(tok)
            status = "ok" if tok else "failed"
            print(f"  {email}: {status}")

        valid = [(i, t) for i, t in enumerate(tokens) if t]
        if not valid:
            print("No users could log in.")
            return 1
        print(f"  {len(valid)}/{len(demo_users)} users ready")

        async def post_as_user(idx: int, url: str, json: dict[str, Any]) -> tuple[int, dict | None]:
            user_idx, token = valid[idx % len(valid)]
            async with sem:
                await asyncio.sleep(delay * (0.5 + random.random()))
                resp = await client.post(
                    url,
                    json=json,
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code in (200, 201):
                    return (user_idx, resp.json())
                return (user_idx, None)

        # 2. Create companies (async, alternating users)
        print(f"\nCreating {n_companies} companies (concurrency={concurrency}, alternating users)...")
        names = (COMPANY_NAMES * 2)[:n_companies]
        tasks = [
            post_as_user(
                i,
                f"{base}/api/v1/crm/customers/",
                {"name": n, "legal_name": n, "type": "business", "enabled": True},
            )
            for i, n in enumerate(names)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        companies = []
        for r in results:
            if isinstance(r, Exception):
                continue
            _, data = r
            if data:
                companies.append(data)
        print(f"  Created {len(companies)} companies")

        company_ids = [c["id"] for c in companies]
        if not company_ids:
            print("No companies created, stopping.")
            return 1

        # 3. Create contacts (async, alternating users, some with company)
        without_count = int(n_contacts * 0.30)
        with_count = n_contacts - without_count
        used_emails: set[str] = set()
        used_phones: set[str] = set()

        def make_contact_payload(i: int) -> dict[str, Any]:
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            fullname = f"{first} {last}"
            email_val = f"{first.lower()}.{last.lower()}.{i}@{DEMO_CONTACT_EMAIL_DOMAIN}"
            phone = f"+5989{random.randint(1000000, 9999999)}"
            while email_val in used_emails:
                email_val = f"{first.lower()}.{last.lower()}.{i}.{random.randint(100, 999)}@{DEMO_CONTACT_EMAIL_DOMAIN}"
            while phone in used_phones:
                phone = f"+5989{random.randint(1000000, 9999999)}"
            used_emails.add(email_val)
            used_phones.add(phone)

            payload: dict[str, Any] = {
                "fullname": fullname,
                "email": email_val,
                "phone": phone,
                "company": "",
                "source": f"populate_{DEMO_SLUG}",
            }
            if i < with_count and company_ids:
                cust = random.choice(companies)
                payload["company"] = cust.get("name", "")
                payload["account_ids"] = [cust["id"]]
            return payload

        contact_payloads = [make_contact_payload(i) for i in range(n_contacts)]

        print(f"\nCreating {n_contacts} contacts (async, alternating users)...")
        tasks = [
            post_as_user(i, f"{base}/api/v1/crm/contacts/", payload)
            for i, payload in enumerate(contact_payloads)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        contacts = []
        for r in results:
            if isinstance(r, Exception):
                continue
            _, data = r
            if data:
                contacts.append(data)
        print(f"  Created {len(contacts)} contacts")

        contact_ids = [c["id"] for c in contacts]
        if not contact_ids:
            print("No contacts created, skipping activities.")

        # 4. Create activities (async, alternating users)
        kinds = ["note", "task", "event", "other"]
        statuses = ["completed", "planned", "completed"]

        def make_activity_payload(i: int) -> dict[str, Any]:
            kind = random.choice(kinds)
            status = random.choice(statuses)
            title = random.choice(ACTIVITY_TITLES)
            occurred = _random_iso_in_last_90_days()
            content: dict[str, Any] = {"body": f"Actividad {DEMO_SLUG} #{i + 1}"}
            if kind == "task":
                content = {"description": content["body"], "status": "done" if status == "completed" else "open"}
            elif kind == "event":
                content = {"start": occurred, "end": occurred, "location": None}
            payload: dict[str, Any] = {
                "kind": kind,
                "title": title,
                "content": content,
                "source": "manual",
                "status": status,
                "occurred_at": occurred,
                "completed_at": occurred if status == "completed" else None,
            }
            if contact_ids and random.random() < 0.7:
                payload["contact_id"] = random.choice(contact_ids)
            if company_ids and random.random() < 0.4:
                payload["customer_id"] = random.choice(company_ids)
            return payload

        activity_payloads = [make_activity_payload(i) for i in range(n_activities)]

        print(f"\nCreating {n_activities} activities (async, alternating users)...")
        tasks = [
            post_as_user(i, f"{base}/api/v1/activities/", payload)
            for i, payload in enumerate(activity_payloads)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        created = sum(1 for r in results if not isinstance(r, Exception) and r[1] is not None)
        print(f"  Created {created} activities")

        print(f"\nDone. {len(companies)} companies, {len(contacts)} contacts, {created} activities.")
        print("(Multiple users alternating, async/concurrent - simulates real-life usage.)")
        return 0


if __name__ == "__main__":
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8093")
    host = DEMO_HOST
    concurrency = int(os.environ.get("POPULATE_CONCURRENCY", "8"))
    delay_ms = float(os.environ.get("POPULATE_DELAY_MS", "50"))
    exit_code = asyncio.run(
        run(
            base_url=base_url,
            host=host,
            concurrency=concurrency,
            delay_ms=delay_ms,
        )
    )
    sys.exit(exit_code)
