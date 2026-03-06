# CRM v2 Follow-up: Integrations Module

## Goal
Centralize external providers used by the platform behind a single integration layer so CRM, agent console, and future modules consume stable contracts instead of provider-specific APIs.

## Starting Point
The repo already has an integrations app in [src/webchat_django/integrations/models.py](/Users/martinotero/moio_projects/moio/src/webchat_django/integrations/models.py) with:
- `IntegrationDefinition`
- `IntegrationInstance`

That is a good base for provider catalog + workspace configuration, but it still needs a contract layer for runtime usage.

## Proposed Scope
- Providers: WhatsApp, Zeta Software, Google Places, Google Maps, email, SMTP, and future connectors.
- Configuration: workspace-level enablement, secrets, auth metadata, testing, status, and capability flags.
- Contracts: simplified service interfaces consumed by the platform, for example:
  - `ContactLookupProvider`
  - `GeoLookupProvider`
  - `MessageDeliveryProvider`
  - `EmailDeliveryProvider`
  - `ERPAccountSyncProvider`
- Runtime selection: choose active provider instance per contract and workspace.
- Observability: test endpoint, last health result, last sync result, and normalized error payloads.

## Recommended Model Evolution
- Keep `IntegrationDefinition` as the provider catalog.
- Keep `IntegrationInstance` as the workspace binding and credential holder.
- Add `IntegrationCapability` or encode capabilities in definition metadata.
- Add `IntegrationContractBinding`:
  - `workspace`
  - `contract_key`
  - `integration_instance`
  - `is_primary`
  - `settings`
- Add service adapters in Python so CRM and other modules call contracts, not provider-specific code.

## Why This Fits CRM v2
- CRM now owns clean domains: accounts, contacts, deals, tickets, activities, capture, and knowledge.
- External enrichment or sync should enter through contracts, not directly from CRM views or models.
- Capture and knowledge can later call integrations for enrichment without coupling CRM to Google, WhatsApp, or Zeta-specific payloads.

## Delivery Order
1. Normalize the current integrations app around definitions, instances, and contract bindings.
2. Add REST endpoints for contract bindings and provider health checks.
3. Implement the first contracts:
   - `GeoLookupProvider` for Google Maps/Places
   - `MessageDeliveryProvider` for WhatsApp
   - `EmailDeliveryProvider` for SMTP/email
4. Add UI to manage provider instances and contract assignment.
5. Move CRM-side external calls to these contracts.
