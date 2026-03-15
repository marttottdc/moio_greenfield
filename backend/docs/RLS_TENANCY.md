# Row-Level Security (RLS) Tenancy

Single public schema with PostgreSQL RLS by **tenant_id**. Safe for **async + PgBouncer** (no schema switching).

**RLS is enforced at database level by default** when using PostgreSQL (when `DATABASE_URL` is set). Set `USE_RLS_TENANCY=0` to disable (e.g. local SQLite or debugging).

## Enable RLS mode

1. **Environment**
   - With Postgres: RLS defaults to **on** (`USE_RLS_TENANCY` defaults to true when `DATABASE_URL` is set).
   - To disable: `USE_RLS_TENANCY=0`
   - Local dev (e.g. `dev_local_settings`): defaults to `USE_RLS_TENANCY=0`; set `USE_RLS_TENANCY=1` to test RLS locally.

2. **Database**
   - Use standard PostgreSQL (no django-tenants engine): `ENGINE=django.db.backends.postgresql`
   - All tenant-scoped tables live in **public** with a `tenant_id` FK; RLS filters by this column.

3. **Migrations**
   - With RLS enabled, run: `python manage.py migrate`
   - RLS policies use **tenant slug** (`tenancy.0002_rls_policy_tenant_slug`): middleware sets `app.current_tenant_slug`, policies filter by slug via `portal_tenant`. No backfill of `tenant_uuid` needed for visibility.

4. **Reset from schema-per-tenant (dev)**
   - Drop tenant schemas if you had them: `DROP SCHEMA IF EXISTS demo CASCADE;` (repeat for each tenant schema).
   - Run `migrate` with `USE_RLS_TENANCY=1` so all apps apply to public.
   - Create one tenant and user (e.g. via admin or shell); the central RLS middleware sets `app.current_tenant_slug` from the resolved `request.tenant.rls_slug`.

## How it works

- **Middleware** (`tenancy.rls_middleware.TenantAndRLSMiddleware`): central point for tenant + RLS. Runs after `TenantMiddleware` and `AuthenticationMiddleware`. For **public/external** routes it only sets `app.current_tenant_slug = __none__` (no auth). For **tenant/optional** routes it runs DRF authentication, resolves tenant (JWT, user, host or API key), binds `request.tenant` and sets `SET LOCAL app.current_tenant_slug`; if the route requires a tenant and none was resolved, it raises so the request is rejected. Public/external endpoints do not use tenant. Slug is the tenant’s **subdomain** (obligatorio).
- **Policies**: each tenant-scoped table has RLS enabled and **FORCE ROW LEVEL SECURITY**. A row is visible if (1) it belongs to the current tenant (subdomain = current slug), or (2) it belongs to the **platform** tenant (subdomain = `'platform'`, the root). So any user sees their own tenant’s rows plus platform (root) rows.
- **Models**: `TenantScopedModel` has `tenant_id` (FK) and optionally `tenant_uuid` (denormalized). RLS is based on `tenant_id` by resolving `app.current_tenant_slug` to tenant id. **Tenant.subdomain** is obligatorio (null=False); no puede haber tenants sin subdomain.
- **Platform (root)**: el tenant con **subdomain = `'platform'`** es el root; sus filas son visibles para todos los usuarios. Crear un tenant con subdomain `'platform'` para datos compartidos de plataforma.

## Flows / other apps without TenantScopedModel

Apps that use `models.Model` + `tenant = ForeignKey(Tenant)` (e.g. `flows`) do not get `tenant_uuid` from the base class. For full RLS on those tables you can:

- Add `tenant_uuid = models.UUIDField(null=True, db_index=True, editable=False)` and a migration, then add them to the RLS migration table list and backfill; or
- Tenant and RLS are set centrally by `TenantAndRLSMiddleware`; use `request.tenant` in views. For tables that still need RLS/tenant_uuid, add `tenant_uuid` and RLS policy as needed.

## Local dev with RLS

In `dev_local_settings.py`, set:

```bash
export USE_RLS_TENANCY=1
```

Then start the app; DB engine will be `postgresql` and RLS middleware will run.
