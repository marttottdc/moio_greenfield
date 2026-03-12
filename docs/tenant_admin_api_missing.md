# Tenant Admin – API Status

## Implemented (backend)

| Endpoint | Notes |
|----------|--------|
| **GET /api/tenant/bootstrap/** | Returns tenant-admin payload: tenant, workspace, role, currentUser, **users** (from same tenant), and empty workspaces/skills/automations/integrations/plugins. |
| **POST /api/tenant/users/** | Create/update tenant user. Body: `email`, `displayName?`, `password?` (required for new), `role` (admin\|member\|viewer), `isActive?`, `membershipActive?`. |
| **POST /api/tenant/users/delete/** | Delete tenant user. Body: `id?` or `email?`. Cannot delete self. |

Auth: same as main app (JWT via `TenantJWTAAuthentication`, `BearerTokenAuthentication`). User must belong to a tenant; list/save/delete users require `users_manage` capability (e.g. tenant_admin role).

## Fallback when /api/tenant not available

| UI need | Fallback |
|--------|----------|
| Bootstrap | **GET /api/v1/bootstrap/** — frontend maps to `TenantBootstrapPayload` and fills users/workspaces/… as empty. |

## Workspaces, skills, automations, integrations, plugins

These are **not** implemented as Django REST endpoints for Tenant Admin. They are tied to the **agent console runtime**:

- **`backend/moio_runtime/`** — Runtime used by the agent console (chatbot):
  - **Workspaces**: `workspace_slug` and `workspace_root` in config; `StandaloneAgentBackend(tenant_schema=…, workspace_slug=…)`. Workspace profile/skills come from `workspace_profile_resolver` / `workspace_skills_resolver` (callbacks).
  - **Skills**: `moio_runtime/skills.py` — `load_skills(skill_dirs, enabled_keys)` from config; skills loaded from files (e.g. `SKILL.md`). Config: `config.toml` → `[skills]` (directories, enabled), env `REPLICA_SKILL_DIRS`, `REPLICA_SKILLS_ENABLED`.
  - **Plugins**: `moio_runtime/plugins.py`, `config.py` — `PluginsConfig` (manifests_dir, platform_approved, tenant_enabled, user_allowed, etc.). Resolved per tenant/workspace at runtime.
- **`backend/chatbot/`** — Desktop agent API under `api/v1/desktop-agent/`; uses `moio_runtime` for sessions, resources, agents. Runtime resources/skills/plugins are exposed via the runtime backend, not via a separate tenant CRUD API.

So for Tenant Admin UI: **workspaces**, **skills**, **automations**, **integrations** (tenant bindings), **plugins** (tenant enablement/assignments) would need either (a) new Django APIs that persist to a store the runtime reads, or (b) runtime/config APIs if the runtime exposes them. Currently they are **not** implemented as REST endpoints; the UI will show empty lists or 404 for those actions.

## Summary

- **Implemented:** GET /api/tenant/bootstrap/, POST /api/tenant/users/, POST /api/tenant/users/delete/ (main app JWT or tenant session).
- **Fallback:** GET /api/v1/bootstrap/ when /api/tenant/bootstrap is not used.
- **Not implemented (runtime/config):** Workspaces, skills, automations, tenant integrations, tenant plugins — see agent console runtime (`moio_runtime`, `chatbot`) and config; add REST only if you need Tenant Admin to persist them in Django.
