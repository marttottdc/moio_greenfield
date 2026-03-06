# Flow Builder data integrations

> ℹ️ See also: [`flow-builder-react-integration.md`](./flow-builder-react-integration.md) for the complete React integration contract, including DOM bootstrap details, API endpoints, and feature parity requirements when working from an external repository.

The React Flow Builder now fetches the same supporting datasets that powered the legacy `builder_render.js` module. These helpers keep the new UI aligned with the original automation requirements and avoid duplicating fetch logic across forms.

## Webhook directory
- **List endpoint**: `GET /webhooks/` (accepts an optional `flow_id` query param to scope results).
- **Create endpoint**: `POST /webhooks/register` – returns the created webhook record in the legacy shape (id, name, url, description, `handler_path`, `expected_content_type`).
- **Hook**: `useWebhookList(flowId)` normalises responses and caches them via React Query.
- **Create mutation**: `useCreateWebhookMutation()` posts the payload and rehydrates the cache. The provider automatically injects the current `flowId` so downstream forms don't need to remember it.
- **Context**: `useWebhookData()` surfaces `webhooks`, loading/error flags, `refresh()`, and `createWebhook()` so `NodeConfigForms` can render dropdowns and launch the "create webhook" dialog without duplicating fetches.

## WhatsApp templates
- **Endpoint**: `GET /campaigns/whatsapp/templates/` (defaults to the `WhatsApp` channel, matching the campaign wizard and legacy builder implementation).
- **Hook**: `useWhatsAppTemplates(channel)` normalises template payloads, including placeholders and component previews.
- **Context**: `useTemplateData()` exposes cached template collections, loading/error state, and a `refresh()` helper for the WhatsApp template configuration form.

## Provider usage
Wrap the builder canvas with the shared providers so any node form can grab the cached datasets:

```tsx
import { BuilderDataProviders } from "@/components/flow/BuilderDataContext";

<ReactFlowProvider>
  <BuilderDataProviders flowId={flowId}>
    <FlowCanvas flowId={flowId} />
  </BuilderDataProviders>
</ReactFlowProvider>
```

`WebhookForm` and `WhatsAppTemplateForm` now consume the contexts to show searchable pickers, error/empty states, and live previews that mirror the legacy modal experience.
