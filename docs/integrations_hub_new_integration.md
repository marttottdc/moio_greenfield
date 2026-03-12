# Adding a New Integration (Integrations Hub)

This document describes the procedure to add a new integration to the platform under the **Integrations Hub Contract**. Follow these steps in order.

---

## 1. Register the definition

**File:** `backend/central_hub/integrations/registry.py`

Add an entry to `INTEGRATION_REGISTRY` with:

- **Identity:** `slug`, `name`, `description`, `category`, `icon`
- **Multi-instance:** `supports_multi_instance` (e.g. `True` for WhatsApp/Shopify, `False` for single config per tenant)
- **Contract fields:**
  - `auth_scope`: `"global"` | `"tenant"` | `"user"` (credentials scope)
  - `supports_webhook` / `supports_oauth` / `supports_polling`: transport capabilities
  - `webhook_path_suffix`: e.g. `"myprovider"` → path will be `.../myprovider/webhook/`
  - `adapter_module`: dotted path to your adapter class, e.g. `"central_hub.integrations.myprovider.adapter.MyProviderAdapter"`
- **Schema:** `fields` list of `IntegrationField` (name, type, required, sensitive, description, etc.)

Example (minimal):

```python
"myprovider": IntegrationDefinition(
    slug="myprovider",
    name="My Provider",
    description="Connect to My Provider API",
    category="services",
    icon="plug",
    supports_multi_instance=False,
    auth_scope="tenant",
    supports_webhook=True,
    supports_oauth=False,
    webhook_path_suffix="myprovider",
    adapter_module="central_hub.integrations.myprovider.adapter.MyProviderAdapter",
    fields=[
        IntegrationField(name="api_key", required=True, sensitive=True, description="API key"),
        IntegrationField(name="endpoint", default="https://api.myprovider.com", description="API base URL"),
    ],
),
```

---

## 2. Create the adapter

**Location:** `backend/central_hub/integrations/<slug>/adapter.py` (or `adapters/myprovider_adapter.py` for a single file).

Create a class that subclasses `IntegrationAdapter` from `central_hub.integrations.contract` and implements:

| Method | Required | Purpose |
|--------|----------|---------|
| `connect(tenant_id, instance_id, credentials)` | Yes | OAuth/connect flow; return `{ "instance_id", "status" }`. |
| `disconnect(tenant_id, instance_id)` | Yes | Disable binding and clear secrets. |
| `validate(tenant_id, instance_id, config)` | Yes | Check credentials; return `(success: bool, message: str)`. |
| `sync(tenant_id, instance_id, options)` | No | Run sync; default returns `{"status": "skipped"}`. |
| `handle_webhook(request, topic, payload, headers)` | No | Verify + dispatch webhook; raise `NotImplementedError` if no webhooks. |
| `health(tenant_id, instance_id)` | No | Return status/last_ok for UI. |
| `public_summary(tenant_id, instance_id)` | No | Safe summary for hub (no secrets). |

Set `slug = "myprovider"` on the class. Use `IntegrationConfig.get_for_tenant()` / `IntegrationConfig.objects.filter(...)` to read and update binding state; set `IntegrationBindingStatus` and `config` / `enabled` as needed.

Reference implementations:

- **Shopify:** `backend/central_hub/integrations/shopify/adapter.py` (webhook, OAuth, token from installation)
- **WhatsApp:** `backend/central_hub/integrations/whatsapp/adapter.py` (webhook delegation, multi-instance)

---

## 3. Wire URLs (webhook, OAuth, embed)

- **Generic CRUD** for your slug is already provided under `/api/v1/integrations/<slug>/` and `/<slug>/<instance_id>/` (list, get, patch, delete, test). No extra URLs needed for simple API-key integrations.

- **Webhook:** If the integration has webhooks, add a dedicated subpackage and URL include:
  - Create `backend/central_hub/integrations/myprovider/urls.py` with a path for the webhook view (e.g. `path("webhook/", myprovider_webhook_receiver)`).
  - In `backend/central_hub/integrations/urls.py`, add:  
    `path("myprovider/", include("central_hub.integrations.myprovider.urls"))`  
  - Webhook URL becomes: `/api/v1/integrations/myprovider/webhook/`.  
  - In the adapter, implement `handle_webhook` (verify signature, resolve tenant/instance, enqueue tasks).

- **OAuth / embedded app:** Add views for install, callback, and (optional) embed config/link/sync, and register their paths under the same `myprovider/` include (see `central_hub/integrations/shopify/urls.py`).

---

## 4. Persist binding state and config

- **Standard case:** Use **`IntegrationConfig`** only. One row per `(tenant, slug, instance_id)`. Set `status` (e.g. `IntegrationBindingStatus.CONNECTED`), `enabled`, and `config` (JSON). When creating/updating after OAuth or connect, set `status` and optionally clear secrets on disconnect.

- **Provider-specific models (optional):** If the provider has its own “installation” or “link” (e.g. Shopify’s `ShopifyShopInstallation` + `ShopifyShopLink`), add models in `central_hub/integrations/models.py` (or in the integration’s `models.py` and import in central_hub). Keep **credentials** in the provider model or in a single source of truth; use a helper (e.g. `get_shopify_config_for_sync`) so sync/tasks read merged config (settings from `IntegrationConfig` + token from installation). Still use `IntegrationConfig` as the binding record for the hub (status, enabled, instance_id).

---

## 5. Sync / background tasks

- Resolve config by **tenant + instance_id** (and, if needed, by provider identity such as shop_domain).
- Prefer a **config helper** (e.g. `get_shopify_config_for_sync(tenant_id, instance_id)`) that returns a single config dict (including token from installation when applicable). Use it in Celery tasks so they always use the same source of truth.
- In the task, get tenant and config; if config is missing or disabled, return `{"status": "skipped", "reason": "..."}`. Otherwise call your sync service and update `IntegrationConfig.metadata` (e.g. last_sync, last_id) as needed.
- For **webhooks:** In the webhook handler, resolve tenant and instance_id from the payload/headers (e.g. shop_domain, phone_id), then enqueue a task with `tenant_id` and `instance_id` so the task uses the same resolution as manual sync.

---

## 6. Frontend (optional)

- **Settings / hub:** The list endpoint `GET /api/v1/integrations/` already returns your integration once it’s in the registry (with `auth_scope`, `supports_webhook`, `binding_statuses`, etc.). The generic config UI uses `GET/PATCH /api/v1/integrations/<slug>/` and `/<slug>/<instance_id>/`.
- **Custom UI:** Add a page or section that calls your embed/config endpoints (if any) and uses `public_summary` or config GET for display. Add the route in the frontend router and, if needed, an entry in the sidebar or settings.

---

## Checklist

- [ ] Entry in `INTEGRATION_REGISTRY` with slug, auth_scope, transport flags, `adapter_module`, `webhook_path_suffix`, and `fields`.
- [ ] Adapter class implementing `connect`, `disconnect`, `validate`; optionally `sync`, `handle_webhook`, `health`, `public_summary`.
- [ ] Webhook URL under `/api/v1/integrations/<slug>/webhook/` and adapter `handle_webhook` (if webhooks).
- [ ] OAuth/embed URLs and views (if applicable).
- [ ] Binding state in `IntegrationConfig` (and optional provider models); set `status` on connect/disconnect.
- [ ] Sync tasks and optional config helper using tenant + instance_id (and provider identity if needed).
- [ ] Frontend: rely on generic integration list/detail or add custom UI.

---

## Auth scope summary

| auth_scope | Meaning | Example |
|------------|---------|---------|
| **global** | One platform-wide credential set (e.g. app id/secret). | Shopify app credentials in PlatformConfiguration. |
| **tenant** | One credential set per tenant (or per instance if multi-instance). | Shopify store per tenant, WhatsApp number per tenant. |
| **user** | One credential set per user. | Gmail, Google Calendar (future). |

Use **tenant** for most B2B integrations; use **user** when the connection is tied to a user identity (e.g. OAuth with user scope).
