# Shopify Embedded App Setup

This document describes how to configure and deploy the Shopify embedded app integration.

**Theme app extension (chat widget):** The repo includes `shopify.app.toml` and `extensions/chat-widget/`. To publish or update the widget, fill the toml from platform config then deploy: `cd backend && python manage.py shopify_write_app_toml` (writes `client_id` and `application_url` from PlatformConfiguration), then from repo root `shopify app deploy`. See `extensions/chat-widget/README.md`.

## Configuration overview

| Setting | Where it lives | Who can change it |
|--------|----------------|-------------------|
| **App URL** (public base URL) | `PlatformConfiguration.my_url` | Platform administrators only |
| **Shopify Client ID** | `PlatformConfiguration.shopify_client_id` | Platform administrators only |
| **Shopify Client Secret** | `PlatformConfiguration.shopify_client_secret` | Platform administrators only |
| **Per-shop connection** (store URL, sync toggles) | `IntegrationConfig` (slug `shopify`) | Tenant users for their linked shop |

Platform-level settings are managed in **Platform Admin**. The embedded merchant-facing page does **not** allow editing client ID, client secret, or app URL.

## URLs to register in Shopify Partner Dashboard

After setting **App URL** in Platform Admin, use these derived URLs in your Shopify app configuration:

- **App URL (embedded app):** `{App URL}/apps/shopify/app`  
  Example: `https://your-domain.com/apps/shopify/app`

- **Allowed redirection URL(s) (OAuth):** `{App URL}/api/v1/integrations/shopify/oauth/callback/`

- **Webhook endpoint:** `{App URL}/api/v1/integrations/shopify/webhook/`  
  Mandatory GDPR/lifecycle topics are registered automatically after install:  
  `app/uninstalled`, `customers/data_request`, `customers/redact`, `shop/redact`.

## Where to set Client ID and Client Secret

1. **Platform Admin (recommended)**  
   Log in as a platform administrator and use the Platform Admin UI to set **App URL**, **Shopify Client ID**, and **Shopify Client Secret**. These are stored in `PlatformConfiguration`.

2. **Database**  
   For automation or initial setup, you can set `platform_configuration.shopify_client_id` and `platform_configuration.shopify_client_secret` (and `my_url`) directly. Prefer environment or secrets management for the client secret in production.

3. **Environment / secrets (future)**  
   The codebase may be extended to support an env var or secret-manager override for the client secret while keeping the client ID in the database.

## Admin API access scopes

The app requests these [authenticated access scopes](https://shopify.dev/docs/api/usage/access-scopes) at install (OAuth):

| Scope | Used for |
|-------|----------|
| `read_products` | Sync products, product variants |
| `read_customers` | Sync customers |
| `read_orders` | Sync orders |
| `read_inventory` | Sync inventory levels (receive_inventory) |

They are defined in code as `SHOPIFY_SCOPES`. In the **Shopify Partner Dashboard**, your app’s **Configuration → Admin API integration** (or **API access scopes**) must include these scopes. If you add a new scope in code, merchants must **re-install the app** so Shopify issues a new token with the updated scopes.

## Deployment checklist

- [ ] **App URL** is set to your public base URL (tunnel in dev, e.g. `https://your-app.ngrok.io`, or production domain).
- [ ] **Shopify Client ID** and **Client Secret** are set in Platform Configuration (or equivalent).
- [ ] In Shopify Partner Dashboard, **App URL** is set to `{your base URL}/apps/shopify/app`.
- [ ] In Shopify Partner Dashboard, **Allowed redirection URL(s)** include `{your base URL}/api/v1/integrations/shopify/oauth/callback/`.
- [ ] In Shopify Partner Dashboard, **Admin API access scopes** include `read_products`, `read_customers`, `read_orders`, `read_inventory` (see [Access scopes](https://shopify.dev/docs/api/usage/access-scopes)).
- [ ] **Frame-ancestors (CSP):** The host that serves the frontend HTML (e.g. your SPA server or reverse proxy) must set `Content-Security-Policy: frame-ancestors https://admin.shopify.com https://*.myshopify.com` for routes under `/apps/shopify` so the app can be embedded in Shopify Admin. Without this, Shopify’s security checks may reject the app.
- [ ] **HTTPS:** Use HTTPS in development (e.g. ngrok, cloudflared) and production.

## Embedded app auth

The embedded page at `/apps/shopify/app` uses **Shopify session tokens** (App Bridge `getSessionToken`) to authenticate API requests. No moio JWT is required for merchants using the app inside Shopify Admin. Platform administrators can still use the rest of the app with normal login.

## Webhooks

- The app registers **app/uninstalled**, **customers/data_request**, **customers/redact**, and **shop/redact** with Shopify after each OAuth install.
- Incoming webhooks are verified with **X-Shopify-Hmac-Sha256** using the app’s client secret.
- Uninstall and GDPR handlers respond with `200` and perform cleanup or redaction as required.

**Critical for uninstall:** The webhook endpoint must be reachable at **exactly**  
`{App URL}/api/v1/integrations/shopify/webhook/`  
(e.g. `https://your-domain.com/api/v1/integrations/shopify/webhook/`). If requests go through a reverse proxy (e.g. Node in front of Django), the proxy **must** forward all `X-Shopify-*` headers (e.g. `X-Shopify-Hmac-Sha256`, `X-Shopify-Topic`, `X-Shopify-Shop-Domain`) so the backend can verify HMAC and process the event.

---

## Uninstall and reinstall (step-by-step)

### Uninstall path

1. **Merchant uninstalls the app in Shopify**  
   (Shopify Admin → Apps → [Your app] → Uninstall.)

2. **Shopify sends a webhook**  
   - **URL:** `POST {App URL}/api/v1/integrations/shopify/webhook/`  
   - **Topic:** `app/uninstalled`  
   - **Body:** JSON including `shop` (e.g. `example.myshopify.com`).

3. **Backend processes the webhook (in order)**  
   - Marks `ShopifyShopInstallation` for that shop as uninstalled and **clears the stored access token** (so it is never used again).  
   - Disables **all** `IntegrationConfig` records for that shop (any tenant) and sets status to `UNINSTALLED`; removes `access_token` from config.  
   - Sets all `ShopifyShopLink` records for that shop to `UNLINKED`.

4. **Result**  
   Our side is fully cleared for that shop: no token, no enabled config, no linked tenant. Sync and API calls for that shop will fail until the app is reinstalled and linked again.

### Reinstall path

1. **Merchant installs the app again from Shopify**  
   (e.g. from the App Store or a direct install link.)

2. **OAuth flow runs**  
   - Backend receives the OAuth callback, exchanges code for a new access token.  
   - Updates or creates `ShopifyShopInstallation` with the **new token** and clears `uninstalled_at`.  
   - Registers GDPR/lifecycle webhooks with Shopify again.

3. **Linking and full config**  
   - After uninstall, all links were set to `UNLINKED`, so there is no linked tenant yet.  
   - Merchant opens the embedded app in Shopify Admin. The embed page will show a “Sign in and continue” (or equivalent) flow.  
   - When the merchant completes **embed/link** (POST to `/api/v1/integrations/shopify/embed/link/` with a valid Shopify session token and moio auth), the backend:  
     - Creates or updates `ShopifyShopLink` (LINKED) for that shop and tenant.  
     - Calls `_ensure_shopify_integration_config`, which **writes the full config** (store URL, access token, direction, sync toggles) into `IntegrationConfig` and sets status to `CONNECTED`.  
   - That single function is used both when linking from the embed and when OAuth runs and a link already exists (e.g. reinstall without having run uninstall webhook).

4. **Result**  
   Full config is persisted; sync and settings work for that shop and tenant again.
