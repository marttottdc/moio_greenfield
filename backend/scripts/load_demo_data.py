#!/usr/bin/env python3
"""
Load CSV dumps into public schema and set tenant_uuid from the demo tenant.

Usage (after migrate, with demo tenant in portal_tenant):
  python scripts/load_demo_data.py [--dump-dir demo_dump] [--schema-name demo]

- Reads CSV files from --dump-dir (default: demo_dump).
- For each <table>.csv, inserts rows into public.<table>.
- If public table has a tenant_uuid column, sets it to the tenant's tenant_code
  (tenant identified by schema_name = --schema-name in portal_tenant).
- Tables without tenant_id/tenant_uuid in public are loaded as-is.

Requires: DATABASE_URL or DB_* env, and a row in public.portal_tenant with
schema_name matching --schema-name (e.g. 'demo').
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

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
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None
    execute_values = None  # type: ignore


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
        raise RuntimeError("Install psycopg2 or run with Django so DB config is available.")
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


def get_public_columns(cursor, table: str):
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """, [table])
    return [row[0] for row in cursor.fetchall()]


def get_public_column_types(cursor, table: str):
    cursor.execute("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
    """, [table])
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_columns_in_unique_constraints(cursor, table: str):
    """Return set of column names that participate in a UNIQUE index (not PK).
    Empty string in these columns should be loaded as NULL so multiple rows are allowed."""
    cursor.execute("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid
            AND a.attnum = ANY(i.indkey) AND a.attnum > 0 AND NOT a.attisdropped
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = %s
          AND i.indisunique AND NOT i.indisprimary
    """, [table])
    return {row[0] for row in cursor.fetchall()}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Load CSV dumps into public and set tenant_uuid")
    parser.add_argument("--dump-dir", default="demo_dump", help="Directory with <table>.csv files")
    parser.add_argument("--schema-name", default="demo", help="portal_tenant.schema_name for the tenant (e.g. demo)")
    args = parser.parse_args()
    dump_dir = Path(args.dump_dir)
    schema_name = args.schema_name.strip()
    if not dump_dir.is_dir():
        print(f"Not a directory: {dump_dir}", file=sys.stderr)
        sys.exit(1)

    params = get_connection_params()
    if not params.get("dbname") or not params.get("user"):
        print("Set DATABASE_URL or DB_HOST, DB_NAME, DB_USER, DB_PASSWORD", file=sys.stderr)
        sys.exit(1)

    if USE_DJANGO:
        connection.ensure_connection()
        conn = connection.connection
    else:
        conn = psycopg2.connect(**params)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, tenant_code FROM portal_tenant WHERE schema_name = %s LIMIT 1",
            [schema_name],
        )
        row = cur.fetchone()
        if not row:
            print(f"No tenant with schema_name={schema_name!r} in portal_tenant. Create it first.", file=sys.stderr)
            sys.exit(1)
        tenant_id, tenant_uuid = row[0], row[1]
        if not tenant_uuid:
            print("Tenant has no tenant_code. Set it (e.g. UUID) and retry.", file=sys.stderr)
            sys.exit(1)
        tenant_uuid_str = str(tenant_uuid)

    # Disable FK checks so we can load in any order (CSV files are alphabetical)
    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")
    conn.commit()

    csv_files = sorted(f for f in dump_dir.iterdir() if f.suffix.lower() == ".csv")
    if not csv_files:
        print(f"No CSV files in {dump_dir}", file=sys.stderr)
        sys.exit(1)

    for path in csv_files:
        table = path.stem
        with conn.cursor() as cur:
            pub_cols = get_public_columns(cur, table)
            if not pub_cols:
                print(f"Skip {table}: no public table")
                continue
            col_types = get_public_column_types(cur, table)
            unique_columns = get_columns_in_unique_constraints(cur, table)
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                dump_cols = reader.fieldnames or []
                rows = list(reader)
            if not rows:
                print(f"Skip {table}: empty CSV")
                continue
            # Columns to insert: only those that exist in both public and CSV, plus tenant_uuid if in public
            insert_cols = [c for c in pub_cols if c in dump_cols or c == "tenant_uuid"]
            if not insert_cols:
                print(f"Skip {table}: no matching columns")
                continue
            has_tenant_uuid = "tenant_uuid" in pub_cols
            if has_tenant_uuid and "tenant_uuid" not in insert_cols:
                insert_cols.append("tenant_uuid")
            # Remap tenant_id: use integer id for FK columns, UUID string for uuid-typed columns
            tenant_id_col = "tenant_id" in pub_cols and "tenant_id" in insert_cols
            tenant_id_is_uuid = col_types.get("tenant_id") == "uuid"
            # Build row tuples; empty -> None for non-text types and for columns in UNIQUE (allow multiple NULLs)
            def row_tuple(r):
                out = []
                for c in insert_cols:
                    if c == "tenant_uuid":
                        out.append(tenant_uuid_str)
                    elif c == "tenant_id" and tenant_id_col:
                        out.append(tenant_uuid_str if tenant_id_is_uuid else tenant_id)
                    else:
                        val = r.get(c, "")
                        if val == "":
                            dt = col_types.get(c) or ""
                            if dt not in ("character varying", "varchar", "char", "character", "text"):
                                val = None
                            elif c in unique_columns:
                                val = None  # allow multiple rows with NULL in unique column (e.g. phone)
                        out.append(val)
                return tuple(out)
            data = [row_tuple(r) for r in rows]
            cols_sql = ", ".join(f'"{c}"' for c in insert_cols)
            placeholders = ", ".join("%s" for _ in insert_cols)
            sql_one = f'INSERT INTO public."{table}" ({cols_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
            try:
                if execute_values:
                    sql_multi = f'INSERT INTO public."{table}" ({cols_sql}) VALUES %s ON CONFLICT DO NOTHING'
                    execute_values(cur, sql_multi, data, page_size=500)
                else:
                    for t in data:
                        cur.execute(sql_one, t)
            except Exception as e:
                print(f"Error loading {table}: {e}")
                conn.rollback()
                raise
        conn.commit()
        print(f"Loaded {len(rows)} rows -> public.{table}")

    # Re-enable FK checks
    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = DEFAULT")
    conn.commit()

    if not USE_DJANGO:
        conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
