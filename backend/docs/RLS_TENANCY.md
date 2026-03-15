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

- **Middleware** (`tenancy.django_rls_middleware.MoioRLSContextMiddleware`): central point for tenant + RLS. For **public/external** routes it skips transaction and RLS (no `SET LOCAL`). For **tenant/optional** routes it opens a transaction, runs DRF auth, resolves tenant (JWT, user, API key), binds `request.tenant`, then runs `SET LOCAL rls.tenant_id`, `SET LOCAL rls.user_id`, `SET LOCAL app.current_tenant_slug`; if the route requires a tenant and none was resolved, it returns 403. Public/external endpoints do not receive tenant context. Slug is the tenant’s **subdomain** (obligatorio).
- **Policies**: each tenant-scoped table has RLS enabled and **FORCE ROW LEVEL SECURITY**. A row is visible if (1) it belongs to the current tenant (subdomain = current slug), or (2) it belongs to the **platform** tenant (subdomain = `'platform'`, the root). So any user sees their own tenant’s rows plus platform (root) rows.
- **Models**: `TenantScopedModel` has `tenant_id` (FK) and optionally `tenant_uuid` (denormalized). RLS is based on `tenant_id` by resolving `app.current_tenant_slug` to tenant id. **Tenant.subdomain** is obligatorio (null=False); no puede haber tenants sin subdomain.
- **Platform (root)**: el tenant con **subdomain = `'platform'`** es el root; sus filas son visibles para todos los usuarios. Crear un tenant con subdomain `'platform'` para datos compartidos de plataforma.

## Flows / other apps without TenantScopedModel

Apps that use `models.Model` + `tenant = ForeignKey(Tenant)` (e.g. `flows`) do not get `tenant_uuid` from the base class. For full RLS on those tables you can:

- Add `tenant_uuid = models.UUIDField(null=True, db_index=True, editable=False)` and a migration, then add them to the RLS migration table list and backfill; or
- Tenant and RLS are set centrally by `TenantAndRLSMiddleware`; use `request.tenant` in views. For tables that still need RLS/tenant_uuid, add `tenant_uuid` and RLS policy as needed.

## PgBouncer and RLS

The middleware uses `SET LOCAL` for `app.current_tenant_slug`, `rls.tenant_id`, and `rls.user_id`, so values are cleared at transaction end. Pooling behaviour depends on PgBouncer mode:

- **Session pooling (recommended for RLS)**  
  Each client keeps a dedicated connection for the session. `SET LOCAL` works as expected; no cross-request leakage. Recommended config:

  ```ini
  pool_mode = session
  max_client_conn = 1000
  default_pool_size = 20
  ```

- **Transaction pooling**  
  Connections are reused across different clients. Session variables can leak between requests. If you must use transaction pooling:
  - Set `server_reset_query = DISCARD ALL` (or `RESET ALL`) and `server_reset_query_always = 1` in PgBouncer so variables are cleared when the connection is returned to the pool.
  - Prefer `SET LOCAL` in app code (already in use) so at least the transaction boundary clears them; the reset is an extra safeguard.

**Summary**: Use **session** pooling for RLS + session variables; with **transaction** pooling, document reset behaviour and rely on `SET LOCAL` + reset.

## Public and external routes

Routes with policy **public** or **external** (e.g. `/api/platform/`, `/api/docs/`, webhooks, `/api/v1/tenants/`) do not run inside the middleware’s transaction and do not get `request.tenant` or RLS context. Views under these paths must not assume `request.tenant` or read tenant-scoped tables without an explicit context (e.g. `tenant_rls_context(tenant)` when intentionally acting for a tenant). As of the endpoint audit, platform and docs_api views do not rely on `request.tenant`.

## Tables under RLS

The canonical list is in `tenancy.migrations.0002_rls_policy_tenant_slug` (`RLS_TABLES`). It includes CRM, datalab, campaigns, integration_*, agent_*, assistant, agent_session, chatbot_*, tenant_tool_configuration, and related tables. Any new tenant-scoped table must be added to that list (or a follow-up migration) and get the same slug-based policy.

## Local dev with RLS

In `dev_local_settings.py`, set:

```bash
export USE_RLS_TENANCY=1
```

Then start the app; DB engine will be `postgresql` and RLS middleware will run.
