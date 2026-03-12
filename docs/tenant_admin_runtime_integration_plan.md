# Plan: Integrate Agent Console Runtime with Platform (Platform Admin + Tenant Admin)

This plan connects the **agent console runtime** (`moio_runtime`) to **Django/platform** so that:

- **Platform Admin** config points are persisted and feed the runtime (and Tenant Admin where relevant).
- **Tenant Admin** can manage tenant-scoped workspaces, skills, plugins, and automations via REST, with the runtime reading from the same data.

**Design decisions:**

- **Notifications** are a **shared platform feature** (not only agent console): persisted in `PlatformNotificationSettings`, exposed in **GET /api/v1/bootstrap/** as `notification_settings` (CRM, PWA, flows, agent console) and in Platform Admin bootstrap as `notificationSettings`.
- **Integrations are not part of the agent runtime or its config.** External integrations are done only via **plugins or internal tools**. The runtime does not use integration resolvers (e.g. `integration_guidance_resolver`, `tenant_integrations`); any such wiring should be removed or repurposed.
- **Plugins are integrated with tenants from the start:** one design for platform plugin registry + tenant plugin enablement/assignments from day one (no separate “platform plugins first, then tenant” phase). Tenant Admin can enable/assign plugins via tenant-scoped APIs without a later migration step.

---

## Platform Admin config points (current state)

Platform Admin exposes these endpoints and bootstrap fields. **Persisted** vs **stub** and how they feed runtime/tenant:

| Config point | API | Persistence | Feeds runtime / Tenant Admin |
|--------------|-----|-------------|------------------------------|
| **Configuration** | POST /api/platform/configuration/ | ✅ `PlatformConfiguration` (singleton) | Site name, OAuth (Google/Microsoft), WhatsApp, Shopify, etc. Used by auth, integrations, central_hub. |
| **Tenants** | POST/delete /api/platform/tenants/ | ✅ `Tenant` | Runtime scope (tenant_schema). Tenant Admin sees own tenant. |
| **Users** | POST/delete /api/platform/users/ | ✅ `MoioUser` | Tenant Admin users list comes from same model (tenant-scoped). |
| **Integrations (definitions)** | POST/delete /api/platform/integrations/ | ✅ `IntegrationDefinition` | Catalog for CRM/settings and platform-level config only. **Not** used by agent runtime (plugins/internal tools only). |
| **Tenant integrations** | POST /api/platform/tenant-integrations/ | ✅ `TenantIntegration` | For CRM/settings and non-agent use. **Not** fed into agent runtime. |
| **Notifications** | POST /api/platform/notifications/ | ✅ `PlatformNotificationSettings` (singleton) | **Shared platform-wide:** main bootstrap `notification_settings`, Platform Admin `notificationSettings`. Used by PWA, CRM, flows, agent console. |
| **Global skills** | POST/delete /api/platform/skills/ | ❌ Stub | Returns bootstrap; `globalSkills: []`. No model. Runtime uses file/config. |
| **Plugins** | GET/POST /api/platform/plugins/ | ❌ Stub | To be persisted with **tenant plugin bindings from the start** (see Plugins section). |

So today:

- **Real:** Configuration, tenants, users, integration definitions, tenant-integrations, **notifications**.
- **Stubs:** Global skills, plugins (to be implemented with tenant integration from the start).

---

## Current state (runtime vs Django, for integration)

| Area | Runtime (moio_runtime / chatbot) | Django / Platform | Gap |
|------|-----------------------------------|--------------------|-----|
| **Workspaces** | `StandaloneAgentBackend(tenant_schema, workspace_slug)`; config `workspace_root`. No resolvers passed from Django. | No model. | No CRUD; runtime uses a single config + slug. |
| **Skills** | `load_skills(skill_dirs, enabled_keys)` from config/file (e.g. `SKILL.md`). | No model. | File-only; no tenant-scoped DB. |
| **Plugins** | `PluginsConfig`: `tenant_enabled`, `user_allowed`, etc. from config/env. | Platform: `/api/platform/plugins/` (stub). **Plugins to be integrated with tenants from the start.** | Need platform registry + tenant enablement/assignments in one design; runtime reads from DB. |
| **Automations** | Not in runtime. | Flows: `api/v1/flows/` (different model). | No tenant automation template/instance API. |
| **Integrations** | **Not part of agent runtime.** External integrations only via plugins or internal tools. | `TenantIntegration` / Integration definitions for CRM/settings. | No integration resolvers or tenant_integrations in runtime; remove or repurpose if present. |

---

## Integration strategy

**Principle:**

- **Platform Admin** owns **global** config: integration definitions (for CRM/settings only, not agent runtime), global skills, **plugin registry**, platform configuration, **notification settings** (shared platform-wide).
- **Tenant Admin** owns **tenant-scoped** config: **plugins** (enablement/assignments from the start), workspaces, tenant skills, automations. **Integrations** (TenantIntegration) are for CRM/settings only; agent runtime does **not** use them (plugins or internal tools only).
- **Runtime** gets: (1) base config from TOML/env or Platform config, (2) tenant/workspace data from resolvers that query Django: **workspace profile**, **workspace skills**, **plugin tenant_enabled/assignments**. No integration resolvers.

**Order of work (recommended):**

**Phase A — Platform Admin (global) + plugins/tenants from the start**

1. **Notifications** — ✅ Done. `PlatformNotificationSettings` model; POST /api/platform/notifications/ persists; platform bootstrap + **GET /api/v1/bootstrap/** `notification_settings` for whole platform (PWA, CRM, flows, agent console).
2. **Global skills** — Add `GlobalSkill` (or `SkillDefinition`) model; Platform Admin CRUD; include in bootstrap. Runtime can use as “global” skills; tenants reference in workspace enabled_skill_keys.
3. **Plugins (platform + tenant from the start)** — Add plugin registry model(s) **and** tenant plugin binding/assignment models in one go. Implement GET/POST /api/platform/plugins/ (registry) **and** GET/POST /api/tenant/plugins/ (tenant enablement/assignments); include in both bootstraps. Wire runtime to DB for tenant_enabled and plugin_configs so there is no separate “platform-only then tenant” phase.

**Phase B — Tenant Admin (tenant-scoped) and runtime wiring**

4. **Workspaces** — New Workspace model; tenant bootstrap + POST/delete; pass `workspace_profile_resolver` from Django into runtime.
5. **Skills (tenant)** — New TenantSkill model; tenant bootstrap + POST/delete; pass `workspace_skills_resolver` from Django into runtime.
6. **Automations** — New AutomationTemplate + AutomationInstance models; tenant bootstrap + POST/delete; optional runner later.

(Integrations for CRM/settings remain as today; no agent runtime integration resolvers.)

---

## 1. Integrations (tenant-scoped, for CRM/settings only)

**Goal:** Tenant Admin can enable/configure integrations for their tenant (e.g. CRM, settings). **Not** used by the agent runtime — external integrations in the agent are done via **plugins or internal tools** only.

**Backend (optional / existing):**

- **`/api/tenant/integrations/`** (POST) and bootstrap fields `integrations` / `tenantIntegrations` are for CRM and platform settings only. No integration resolvers or `tenant_integrations` payload are passed into the agent runtime.
- If present in runtime code, remove or repurpose: `integration_guidance_resolver`, `integration_status_resolver`, `tenant_integrations_payload` in resources.

---

## 2. Plugins (integrated with tenants from the start)

**Goal:** Platform plugin registry **and** tenant plugin enablement/assignments are designed and implemented together so Tenant Admin can enable/assign plugins from day one (no two-phase “platform first, then tenant”).

**Backend:**

- **Models (single design):**
  - **Platform:** e.g. `PluginDefinition` (or equivalent) for the registry.
  - **Tenant:** e.g. `TenantPlugin` (tenant, plugin_id, is_enabled, config JSON, notes), `TenantPluginAssignment` (tenant, plugin_id, assignment_type, role/user, is_active, notes). Add and migrate in one go.
- **APIs:**
  - **GET/POST /api/platform/plugins/** — Registry CRUD; include in platform bootstrap.
  - **GET /api/tenant/plugins/** — Platform plugins + tenant bindings/assignments for `request.user.tenant`.
  - **POST /api/tenant/plugins/** — Create/update tenant plugin binding and assignments.
- **Bootstrap:** GET /api/tenant/bootstrap/ includes `plugins`, `tenantPlugins`, `tenantPluginAssignments`, `pluginSync` from the start.

**Runtime integration:**

- In **`get_runtime_backend_for_user`** (or wherever `StandaloneAgentBackend` is created), resolve **tenant_enabled** and **plugin_configs** from Django (TenantPlugin, TenantPluginAssignment); set `config.plugins.tenant_enabled` and `config.plugins.plugin_configs`. Optionally **plugin_user_allowlist_resolver** from assignments.

**Frontend:** Point to `/api/tenant/plugins/` and include in tenant bootstrap.

---

## 3. Workspaces

**Goal:** Tenant Admin can create/edit workspaces (name, slug, specialty prompt, default model, enabled skills); runtime uses them per tenant.

**Backend:**

- **Model (new):** e.g. `tenancy.Workspace` or `central_hub.Workspace`:
  - `tenant` (FK), `slug` (unique per tenant), `name`, `display_name`, `specialty_prompt`, `default_vendor`, `default_model`, `default_thinking`, `default_verbosity`, `enabled_skill_keys` (JSON array), `is_active`, `created_at`, `updated_at`.
- **APIs:**
  - **GET /api/tenant/bootstrap/** — Extend with `workspaces`: list of `Workspace` for current tenant.
  - **POST /api/tenant/workspaces/** — Create/update workspace (slug, name, …).
  - **POST /api/tenant/workspaces/delete/** — Delete by id or slug (scope to tenant).
- **Runtime integration:**
  - When creating **`StandaloneAgentBackend`**, pass **`workspace_profile_resolver`**:
    - Callable that loads `Workspace` for current `(tenant_schema, workspace_slug)` from DB and returns a dict: `name`, `displayName`, `specialtyPrompt`, `defaultVendor`, `defaultModel`, `defaultThinking`, `defaultVerbosity`, `enabledSkillKeys`, etc.
  - So runtime no longer relies only on config for workspace profile; it gets it from Django per request/session.

**Frontend:** Already expects `workspaces` in bootstrap and save/delete; wire to new endpoints.

---

## 4. Skills

**Goal:** Tenant Admin can manage tenant-level skills (and optionally workspace-enabled keys); runtime uses DB-driven skill content and enabled list.

**Options:**

- **A. DB-only:** Add model e.g. `tenancy.TenantSkill` or `central_hub.Skill`: `tenant`, `key`, `name`, `description`, `body_markdown`, `is_active`, `created_at`, `updated_at`. Runtime does **not** use files; it gets skill list and content from a **resolver** that queries this model (and optionally global skills from platform).
- **B. File sync:** Keep file-based skills in runtime; add a Django model and API for Tenant Admin CRUD that **writes** to the skill dir (or a per-tenant path) and triggers reload. More complex (file I/O, concurrency).
- **C. Hybrid:** Global skills from platform/files; tenant overrides in DB. Runtime merges: load base from config, overlay from resolver.

**Recommended (A or C):**

- **Backend:**
  - **Model:** e.g. `TenantSkill`: `tenant`, `key`, `name`, `description`, `body_markdown`, `is_active`, `created_at`, `updated_at`. Unique (tenant, key).
  - **APIs:**
    - **GET /api/tenant/bootstrap/** — Include `skills`: `globalSkills` (from platform or config), `tenantSkills` (from DB), `mergedSkills`, `enabledSkillKeys` per workspace (from `Workspace.enabled_skill_keys` or a separate join).
    - **POST /api/tenant/skills/** — Create/update tenant skill.
    - **POST /api/tenant/skills/delete/** — Delete by tenant + key.
- **Runtime integration:**
  - Pass **`workspace_skills_resolver`** when building the backend:
    - Returns list of skill dicts (key, name, content, enabled) for current tenant/workspace: from `TenantSkill` (+ global if any) and `Workspace.enabled_skill_keys`.
  - In **`StandaloneAgentBackend`**, when building system prompt or skill payload, call this resolver instead of (or in addition to) `load_skills(skill_dirs, enabled)` so DB-driven skills are used.

**Frontend:** Already expects skills in bootstrap and save/delete; wire to new endpoints.

---

## 5. Automations

**Goal:** Tenant Admin can manage automation templates and instances (scheduled runs per workspace); optionally wire to runtime or a job runner.

**Backend:**

- **Models (new):** e.g. `central_hub.AutomationTemplate`, `central_hub.AutomationInstance`:
  - **Template:** tenant, key, name, description, instructions_markdown, example_prompt, default_message, icon, category, is_active, is_recommended, created_at, updated_at.
  - **Instance:** tenant, workspace (FK or slug), template (FK), name, message, execution_mode, schedule_type, schedule_time, interval_minutes, weekdays (JSON), is_active, last_run_at, next_run_at, etc.
- **APIs:**
  - **GET /api/tenant/bootstrap/** — Include `automations`: `templates`, `instances`, `runLogs` (can be empty at first).
  - **POST /api/tenant/automations/** — Body: `recordType` (template|instance), plus template or instance fields. Create/update.
  - **POST /api/tenant/automations/delete/** — Delete template or instance (scope to tenant).
- **Execution:** Either:
  - Use existing **flows** (`api/v1/flows/`) and map automation instance to a flow run (scheduled by celery/beat or similar), or
  - Add a small **automation runner** that reads `AutomationInstance` and invokes the runtime or a flow. Out of scope for “integration plan” but needed for “run” to work.

**Frontend:** Already expects automations in bootstrap and save/delete; wire to new endpoints. Run logs can be stub or implemented later.

---

## 6. Runtime wiring summary

In **`get_runtime_backend_for_user`** (or a factory used by chatbot):

- **Workspace profile:** Pass `workspace_profile_resolver=lambda: get_workspace_profile(tenant_schema, workspace_slug)` that queries `Workspace` and returns the dict the runtime already expects.
- **Workspace skills:** Pass `workspace_skills_resolver=lambda: get_workspace_skills(tenant_schema, workspace_slug)` that returns list of skill dicts from `TenantSkill` + `Workspace.enabled_skill_keys`.
- **Plugins:** Before building config, load `TenantPlugin` / `TenantPluginAssignment` for the tenant and set `config.plugins.tenant_enabled` and `config.plugins.plugin_configs` (and optionally resolve `plugin_user_allowlist_resolver` from assignments).
- **Integrations:** Not used by agent runtime (plugins or internal tools only). Do not pass integration resolvers or tenant_integrations into the runtime.
- **Automations:** No direct runtime dependency unless you add “run automation” that triggers the backend; then the runner would read from `AutomationInstance` and call the runtime.

---

## 7. Platform Admin → runtime / Tenant Admin (summary)

| Platform Admin config | Persisted? | Consumed by runtime | Consumed by Tenant Admin |
|-----------------------|------------|---------------------|---------------------------|
| **Configuration** | ✅ PlatformConfiguration | OAuth, WhatsApp, Shopify, etc. (auth) | N/A (global only) |
| **Tenants** | ✅ Tenant | tenant_schema in backend scope | Own tenant in bootstrap |
| **Users** | ✅ MoioUser | N/A | Users list in bootstrap + CRUD |
| **Integration definitions** | ✅ IntegrationDefinition | **Not** (plugins/internal tools only) | Catalog for CRM/settings; tenant integrations for CRM/settings only |
| **Tenant integrations** | ✅ TenantIntegration | **Not** (plugins/internal tools only) | Own tenant’s bindings for CRM/settings |
| **Notifications** | ✅ PlatformNotificationSettings | — | **Shared platform:** main bootstrap `notification_settings`, Platform Admin `notificationSettings` (PWA, CRM, flows, agent console) |
| **Global skills** | ❌ Stub | File/config today | Would be globalSkills in bootstrap |
| **Plugins** | ❌ Stub → to do | Config today → DB (tenant from start) | plugins + tenantPlugins in bootstrap; GET/POST /api/tenant/plugins/ from the start |

After integration:

- **Notifications** → ✅ Done. Model + save; main bootstrap + platform bootstrap.
- **Global skills** → model + Platform CRUD; in bootstrap; runtime can merge with tenant skills via resolver.
- **Plugins** → platform registry **and** tenant bindings/assignments in one design; runtime reads tenant_enabled and config from DB via resolvers.

---

## 8. Implementation order (checklist)

**Phase A — Platform Admin + plugins/tenants from the start**

| # | Task | Deps | Effort (rough) |
|---|------|------|----------------|
| A1 | **Notifications** — ✅ Done. PlatformNotificationSettings; POST persists; main bootstrap `notification_settings` + platform bootstrap | — | — |
| A2 | **Global skills** — GlobalSkill (or SkillDefinition) model; Platform POST/delete /api/platform/skills/; bootstrap globalSkills from DB | None | Medium |
| A3 | **Plugins (platform + tenant from start)** — PluginDefinition + TenantPlugin + TenantPluginAssignment; GET/POST /api/platform/plugins/ and GET/POST /api/tenant/plugins/; both bootstraps; runtime reads tenant_enabled/config from DB | None | Medium |

**Phase B — Tenant Admin + runtime**

| # | Task | Deps | Effort (rough) |
|---|------|------|----------------|
| B1 | **Workspaces** — Workspace model; GET in bootstrap, POST/delete APIs; workspace_profile_resolver in runtime | None | Medium |
| B2 | **Skills (tenant)** — TenantSkill model; GET in bootstrap, POST/delete APIs; workspace_skills_resolver in runtime | Workspaces (for enabled_skill_keys), optional A2 | Medium |
| B3 | **Automations** — AutomationTemplate + AutomationInstance models; bootstrap + POST/delete APIs; optional runner later | None | Medium |

(Integrations for CRM/settings remain as today; no agent runtime integration.)

---

## 9. Docs and tests

- Update **`docs/tenant_admin_api_missing.md`** as each piece is done (mark implemented, remove from “not implemented”).
- Add tests for new tenant API views (scope to tenant, auth, validation).
- Add a short doc in **`backend/moio_runtime/`** or **`backend/chatbot/`** describing how resolvers are supplied from Django (workspace_profile_resolver, workspace_skills_resolver, plugin config from DB) so future changes stay consistent.

---

## Summary

- **Notifications:** ✅ Shared platform feature; persisted; main bootstrap + platform bootstrap.
- **Integrations:** Not part of agent runtime; only plugins or internal tools. CRM/settings integrations remain as today (no runtime wiring).
- **Plugins:** Integrate with tenants from the start: platform registry + tenant enablement/assignments in one design; GET/POST /api/tenant/plugins/ and runtime reading from DB.
- **Workspaces:** New model + APIs + bootstrap; pass `workspace_profile_resolver` from Django into `StandaloneAgentBackend`.
- **Skills:** New model + APIs + bootstrap; pass `workspace_skills_resolver` from Django into runtime.
- **Automations:** New models + APIs + bootstrap; optional runner later.

This plan integrates the agent console runtime with the platform so Tenant Admin uses the same data the runtime uses, persisted in Django, with no integrations in the runtime (plugins or internal tools only).
