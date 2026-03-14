# Moio Chat Widget – Theme App Extension

App embed block that adds a chat bubble to the storefront. Visitors are identified by `anonymous_id` (session) or Shopify `customer_id` when logged in. No JWT required.

## Setup

1. **Shopify CLI**: Fill the toml from platform config, then deploy from repo root:
   ```bash
   cd backend && python manage.py shopify_write_app_toml   # reads PlatformConfiguration (client_id, my_url)
   cd .. && shopify app deploy                             # deploys the theme app extension
   ```
   `shopify_write_app_toml` writes `client_id` and `application_url` into `shopify.app.toml` from PlatformConfiguration (no manual copy). **Run `shopify app deploy` every time you change the widget** (Liquid, JS or CSS). The rest of the app is deployed separately.

2. **Theme Editor**: After deployment, the merchant enables the block in **Online Store > Themes > Customize > App embeds** and turns on "Moio Chat". **All widget configuration is done here** (title, greeting, bubble icon, primary color, position, offsets, window size, which templates to show on). The backend is only used for `ws_url` and whether the app is installed (`enabled`).

3. **App proxy**: The widget still calls `/apps/moio-chat/chat-widget-config` to get `ws_url` and `enabled`. Theme settings override display config; the proxy is set in `shopify.app.toml` (and `shopify_write_app_toml` writes the proxy URL from PlatformConfiguration).

## Files

- `blocks/chat-widget.liquid` – App embed (target: body). Outputs `data-shop`, `data-customer-id` (when logged in), `data-locale`, and a JSON script `#mc-tc` with theme editor settings (title, greeting, position, color, etc.). The JS merges theme config with backend response (backend supplies only `ws_url` and `enabled`).
- `assets/chat-widget.js` – Fetches config, connects to WebSocket (`/ws/shopify-chat/`), sends `init` with `shop_domain`, `anonymous_id`, `customer_id`; handles `send_message` and displays messages.
- `assets/chat-widget.css` – Styles for bubble and chat window.

## Backend

- **App proxy** `GET /api/v1/integrations/shopify/app-proxy/<path>` – Shopify forwards storefront requests from `https://{shop}/apps/moio-chat/...` here. Signature is verified with `shopify_client_secret`; `chat-widget-config` path returns the same JSON as below.
- **GET** `/api/v1/integrations/shopify/chat-widget-config/?shop=xxx.myshopify.com` – Returns **only** `{ "enabled": true, "ws_url": "wss://..." }` when the shop is linked and installed; `{ "enabled": false }` otherwise. All display config (title, greeting, position, etc.) lives in the **theme block** (single source of truth).
- **WebSocket** `/ws/shopify-chat/` – No auth. First message must be `action: "init"` with `shop_domain`, `anonymous_id`, optional `customer_id`. Then `send_message`, `get_history`.

## Rich content messages

Assistant responses can include optional `rich_content` in `bot_message` payloads, with safe rendering for images, links, and buttons.

Supported shape:

```json
{
  "text": "Check this out",
  "rich_content": {
    "items": [
      { "type": "image", "url": "https://cdn.example.com/product.jpg", "alt": "Product", "link_url": "https://shop.example.com/products/1" },
      { "type": "link", "text": "View details", "url": "https://shop.example.com/products/1" },
      { "type": "button", "text": "Buy now", "url": "https://shop.example.com/cart/1:1" }
    ]
  }
}
```

Notes:
- Only `http/https` URLs are rendered.
- If `rich_content` is absent, the widget renders plain text.
- For backward compatibility, if assistant output is a JSON string with the same structure, it is parsed and rendered as rich content.

Agent channel: `shopify_webchat`. Create an agent with channel "Shopify Webchat" (or use the tenant default agent) for storefront replies.
