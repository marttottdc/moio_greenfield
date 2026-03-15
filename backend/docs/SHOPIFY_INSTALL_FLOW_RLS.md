# Flujo de instalación Shopify tras migración a RLS

## Resumen

Tras la migración a RLS (Row-Level Security) por `tenant_slug` (`app.current_tenant_slug`), el flujo de instalación/link de Shopify sigue funcionando si se cumple lo siguiente:

1. **Tablas sin RLS** (globales por shop): `shopify_oauth_state`, `shopify_shop_installation`, `shopify_shop_link`. No tienen `tenant_id`; no están en `RLS_TABLES`. Lecturas/escrituras no dependen del slug.
2. **Tabla con RLS**: `integration_config` tiene `tenant_id` y política por slug. Cualquier lectura/escritura requiere que `app.current_tenant_slug` coincida con el tenant de la fila.
3. **OAuth callback** es ruta **external** (`/api/v1/integrations/shopify/oauth`). No hay usuario ni tenant en el request, por tanto el middleware no setea `app.current_tenant_slug`. Al refrescar un shop ya linkado, se llama a `_ensure_shopify_integration_config(tenant, shop, installation)` y se escribe en `integration_config`. **Sin contexto RLS ese INSERT/UPDATE falla.** Por eso se envuelve la llamada en `tenant_rls_context(tenant.rls_slug)` en el callback.
4. **Embed/link** va con JWT (usuario moio + tenant). El middleware central (TenantAndRLSMiddleware) ejecuta auth, resuelve tenant y setea `request.tenant` y `app.current_tenant_slug`. Las escrituras a `IntegrationConfig` en ese request ya ven el slug correcto.

## Flujo paso a paso

### 1. OAuth Install (GET `/api/v1/integrations/shopify/oauth/install/`)

- **Auth**: ninguna.
- **Ruta**: external → no se resuelve tenant.
- **Acción**: crea `ShopifyOAuthState`, redirect a Shopify.
- **RLS**: no toca tablas con RLS. OK.

### 2. OAuth Callback (GET `/api/v1/integrations/shopify/oauth/callback/`)

- **Auth**: ninguna (Shopify redirige con `code`).
- **Ruta**: external → `app.current_tenant_slug` no se setea.
- **Acción**:
  - Lee/borra `ShopifyOAuthState` (sin RLS).
  - `ShopifyShopInstallation.objects.update_or_create(shop_domain=shop, ...)` (sin RLS).
  - Si existe `ShopifyShopLink` para el shop con status LINKED:
    - **Antes (bug)**: `_ensure_shopify_integration_config(tenant, shop, installation)` corría sin contexto RLS → fallo al escribir en `integration_config`.
    - **Después (fix)**: se ejecuta dentro de `tenant_rls_context(tenant.rls_slug)` para setear `app.current_tenant_slug` y permitir el write en `integration_config`.
  - Redirect al embed app.
- **RLS**: solo afecta a `integration_config`; el fix con `tenant_rls_context` lo cubre.

### 3. Embed Link (POST `/api/v1/integrations/shopify/embed/link/`)

- **Auth**: JWT (usuario moio) + header `X-Shopify-Session-Token`.
- **Ruta**: no está en external; se resuelve tenant por JWT → `request.tenant` y `app.current_tenant_slug` seteados.
- **Acción**:
  - Lee `ShopifyShopInstallation` (sin RLS).
  - Crea/actualiza `ShopifyShopLink` (sin RLS).
  - `_ensure_shopify_integration_config(tenant, shop, installation)` → escribe en `integration_config` con slug ya seteado por el middleware.
- **RLS**: OK; el slug del request coincide con el tenant del usuario.

### 4. Embed Config (GET `/api/v1/integrations/shopify/embed/config/`)

- **Auth**: session token de Shopify **o** JWT moio.
- Si es **session token**: el middleware central ejecuta primero la autenticación DRF; si el auth de session token setea `user.tenant = link.tenant` y devuelve ese user, el middleware luego resuelve tenant desde `request.user` y setea `request.tenant` y `app.current_tenant_slug`. Si en algún caso el tenant no quedara seteado en el request, en `ShopifyEmbedConfigView.get` la lógica que toca `IntegrationConfig` se ejecuta dentro de `tenant_rls_context(tenant.rls_slug)` por seguridad.
- Si es **JWT**: tenant y slug se setean por el middleware central. OK.

## Tablas y RLS

| Tabla                         | RLS | tenant_id | Uso en flujo Shopify        |
|------------------------------|-----|-----------|-----------------------------|
| `shopify_oauth_state`        | No  | No        | Install: create; Callback: read/delete |
| `shopify_shop_installation`  | No  | No        | Callback: update_or_create; Link: read  |
| `shopify_shop_link`          | No  | Sí (FK)   | Callback: read; Link: read/write        |
| `integration_config`        | Sí  | Sí        | Callback (si ya linkado) y Link: write  |
| `portal_tenant`              | No  | N/A       | Usado en política RLS (subquery)        |

## Cambios realizados

### 1. OAuth callback

Al refrescar `IntegrationConfig` para un shop ya linkado, la escritura se ejecuta dentro del contexto RLS del tenant del link:

```python
# ShopifyOAuthCallbackView.get
if link:
    tenant = link.tenant
    slug = getattr(tenant, "rls_slug", None) or getattr(tenant, "subdomain", "") or ""
    with tenant_rls_context(slug):
        _ensure_shopify_integration_config(tenant, shop, installation)
```

### 2. Embed config (GET) con session token

Con auth por session token de Shopify, el middleware no setea `request.tenant` (el usuario se asigna después en DRF). Las lecturas/escrituras a `integration_config` se hacen dentro de `tenant_rls_context(tenant.rls_slug)`:

```python
# ShopifyEmbedConfigView.get
slug = getattr(tenant, "rls_slug", None) or getattr(tenant, "subdomain", "") or ""
with tenant_rls_context(slug):
    config_obj = IntegrationConfig.objects.filter(...).first()
    if config_obj and need_write:
        updated = ensure_shopify_config_persisted_from_link(tenant, instance_id)
```

Así, tras la migración a RLS, el flujo de instalación Shopify (OAuth install → callback → embed link → embed config) sigue siendo correcto y las lecturas/escrituras en `integration_config` son visibles y permitidas por la política por slug.
