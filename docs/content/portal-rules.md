---
title: "Portal Rules & Constraints"
slug: "portal-rules"
category: "integrations"
order: 5
status: "published"
summary: "- `tenant_code` must be unique - `tenant_code` is primary identifier for tenant context"
tags: ["portal"]
---

## Overview

- `tenant_code` must be unique - `tenant_code` is primary identifier for tenant context

# portal - Invariants

## Data Integrity Rules

### Tenant Rules
- `tenant_code` must be unique
- `tenant_code` is primary identifier for tenant context

### MoioUser Rules
- Email must be unique
- Username must be unique
- User must belong to a tenant (nullable for superusers)

### TenantConfiguration Rules
- One configuration per tenant (OneToOne)
- Integration credentials validated per integration type
- `conversation_handler` must be valid: chatbot, assistant, agent

### ExternalAccount Rules
- One account per (tenant, email, provider) combination
- Token refresh required before expiration
- `sync_enabled` controls periodic sync

## Business Logic Constraints

### Tenant Isolation
- All tenant-scoped models filter by `current_tenant`
- `TenantManager` automatically applies tenant filter
- Cross-tenant data access prevented by design

### Authentication
- JWT tokens include tenant_id claim
- Token lifetime: 60 minutes access, 7 days refresh
- Service tokens for service-to-service auth

### Integration Credentials
- WhatsApp requires: WABA ID, Phone ID, Token
- OpenAI requires: API key, model selection
- Google requires: API key
- WooCommerce requires: URL, consumer key, consumer secret
- Psigma requires: user, password, token

## Security Constraints

### Token Management
- Access tokens short-lived (60 min)
- Refresh tokens longer-lived (7 days)
- OAuth tokens refreshed before expiration

### CSRF Protection
- Session auth exempts CSRF for API endpoints
- JWT auth bypasses CSRF
