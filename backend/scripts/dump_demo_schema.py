#!/usr/bin/env python3
"""
Dump all data from PostgreSQL schema `demo` to CSV files.

Usage (from backend/ or project root with DATABASE_URL/DB_* set):
  python scripts/dump_demo_schema.py [--schema demo] [--out demo_dump]

Creates demo_dump/<table>.csv for each table in the given schema.
Requires: DATABASE_URL or DB_HOST, DB_NAME, DB_USER, DB_PASSWORD (and optional DB_PORT).
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

# Optional: use Django DB config if available
try:
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.settings")
    django.setup()
    from django.conf import settings
    from django.db import connection
    USE_DJANGO = True
except Exception:
    USE_DJANGO = False

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def get_connection_params():
    if USE_DJANGO:
        db = connection.settings_dict
        return {
            "host": db.get("HOST", "localhost"),
            "port": db.get("PORT", "5432"),
            "dbname": db.get("NAME"),
            "user": db.get("USER"),
            "password": db.get("PASSWORD"),
        }
    if psycopg2 is None:
        raise RuntimeError("Install psycopg2 or run with Django (DJANGO_SETTINGS_MODULE) so DB config is available.")
    import urllib.parse
    url = os.environ.get("DATABASE_URL")
    if url:
        parsed = urllib.parse.urlparse(url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "dbname": (parsed.path or "").lstrip("/") or None,
            "user": parsed.username,
            "password": parsed.password,
        }
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ.get("DB_NAME"),
        "user": os.environ.get("DB_USER"),
        "password": os.environ.get("DB_PASSWORD"),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Dump schema data to CSV files")
    parser.add_argument("--schema", default="demo", help="Schema to dump (default: demo)")
    parser.add_argument("--out", default="demo_dump", help="Output directory for CSV files (default: demo_dump)")
    args = parser.parse_args()
    schema = args.schema.strip()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if USE_DJANGO:
        conn = connection.connection
        if conn is None:
            connection.ensure_connection()
            conn = connection.connection
    else:
        params = get_connection_params()
        if not params.get("dbname") or not params.get("user"):
            print("Set DATABASE_URL or DB_HOST, DB_NAME, DB_USER, DB_PASSWORD", file=sys.stderr)
            sys.exit(1)
        conn = psycopg2.connect(**params)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = %s
            ORDER BY tablename
        """, [schema])
        tables = [row[0] for row in cur.fetchall()]

    if not tables:
        print(f"No tables found in schema {schema!r}. Nothing to dump.")
        return

    for table in tables:
        path = out_dir / f"{table}.csv"
        with conn.cursor() as cur:
            cur.execute(f'SELECT * FROM "{schema}"."{table}"')
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(colnames)
            w.writerows(rows)
        print(f"Wrote {len(rows)} rows -> {path}")

    if not USE_DJANGO:
        conn.close()
    print(f"Done. Dumped {len(tables)} tables to {out_dir}/")


if __name__ == "__main__":
    main()
