---
title: "Portal Lifecycle"
slug: "portal-lifecycle"
category: "integrations"
order: 3
status: "published"
summary: "- App config registered via `PortalConfig` - Signals imported on ready (`portal.signals`) - Tenant tools sync triggered for new tenants"
tags: ["portal"]
---

## Overview

- App config registered via `PortalConfig` - Signals imported on ready (`portal.signals`) - Tenant tools sync triggered for new tenants

# portal - Lifecycle

## Startup Behavior

- App config registered via `PortalConfig`
- Signals imported on ready (`portal.signals`)
- Tenant tools sync triggered for new tenants

## Runtime Behavior

### Tenant Context Flow

```
Request arrives
  │
  ├── TenantMiddleware.process_request()
  │   │
  │   ├── Authenticate user (JWT/Session)
  │   │
  │   └── Set current_tenant context variable
  │       └── From user.tenant
  │
  ├── TenantManager.get_queryset()
  │   └── Auto-filter by current_tenant
  │
  └── Request processing continues
```

### JWT Token Flow

```
POST /api/token/
  │
  ├── Validate credentials
  │
  ├── TenantJWTAAuthentication:
  │   └── Add tenant_id to token claims
  │
  └── Return access + refresh tokens

Token refresh:
  │
  └── POST /api/token/refresh/
      └── Validate refresh token, return new access token
```

### Email Integration Flow

```
email_ingest() [Celery beat]
  │
  ├── For each sync-enabled ExternalAccount:
  │   │
  │   ├── Check token expiration
  │   │   └── Refresh if needed via token_service
  │   │
  │   ├── Get fetcher for provider:
  │   │   ├── gmail.py for Google
  │   │   ├── outlook.py for Microsoft
  │   │   └── imap.py for generic IMAP
  │   │
  │   ├── Fetch new messages since last_synced_at
  │   │
  │   ├── Normalize via email normalizer
  │   │
  │   └── Store as EmailMessage records
```

### Calendar Integration Flow

```
calendar_ingest() [Celery beat]
  │
  ├── For each sync-enabled calendar account:
  │   │
  │   ├── Refresh OAuth token if needed
  │   │
  │   ├── Get calendar fetcher:
  │   │   ├── google_calendar.py
  │   │   └── outlook_calendar.py
  │   │
  │   ├── Fetch events in date range
  │   │
  │   ├── Normalize via calendar normalizer
  │   │
  │   └── Upsert CalendarEvent records
```

### New Tenant Setup

```
Tenant.post_save signal
  │
  ├── If created:
  │   │
  │   └── transaction.on_commit():
  │       └── Schedule sync_single_tenant_tools_task
  │           └── Creates TenantToolConfiguration for all tools
```

## Shutdown Behavior

No explicit shutdown behavior.
