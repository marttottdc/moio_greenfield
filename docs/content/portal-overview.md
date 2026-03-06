---
title: "Portal Overview"
slug: "portal-overview"
category: "integrations"
order: 1
status: "published"
summary: "Multi-tenant foundation providing tenant management, user authentication, configuration, content blocks, and external integrations (email, calendar)."
tags: ["portal"]
---

## Overview

Multi-tenant foundation providing tenant management, user authentication, configuration, content blocks, and external integrations (email, calendar).

# portal

## Responsibility

Multi-tenant foundation providing tenant management, user authentication, configuration, content blocks, and external integrations (email, calendar).

## What it Owns

- **Tenant**: Multi-tenant organization units
- **MoioUser**: User accounts with tenant association
- **TenantConfiguration**: Per-tenant settings (WhatsApp, OpenAI, integrations)
- **PortalConfiguration**: Global platform settings
- **ContentBlock/ComponentTemplate**: Reusable UI content blocks
- **AppConfig/AppMenu**: App configuration and navigation
- **Instruction**: System prompts and instructions
- **Document**: Document storage
- **Notification**: User notifications

## External Integrations (`integrations/v1/`)

### Email Integration
- **ExternalAccount**: OAuth email account connections
- **EmailAccount**: Email provider configuration (Gmail, Outlook, IMAP)
- **EmailMessage**: Email message storage

### Calendar Integration
- **CalendarEvent**: Synced calendar events
- **CalendarAccount**: Calendar provider connections

### Fetchers
- `gmail.py`: Gmail API fetcher
- `outlook.py`: Outlook API fetcher
- `imap.py`: Generic IMAP fetcher
- `google_calendar.py`: Google Calendar fetcher
- `outlook_calendar.py`: Outlook Calendar fetcher

### Services
- `token_service.py`: OAuth token management
- `email_service.py`: Email sync operations
- `calendar_service.py`: Calendar sync operations
- `accounts.py`: Account management

## Core Components

### Authentication
- `TenantJWTAAuthentication`: Tenant-aware JWT auth
- `CsrfExemptSessionAuthentication`: Session auth without CSRF
- JWT token customization with tenant claims

### Tenant Context
- `TenantMiddleware`: Sets current tenant from user
- `current_tenant`: Context variable for tenant isolation
- `TenantManager`: Queryset filtering by tenant

### RBAC (`rbac.py`)
- Role-based access control
- Permission checking utilities

### Webhooks (`webhooks/`)
- `registry.py`: Handler registry for webhooks
- `utils.py`: Handler resolution utilities

## What it Does NOT Do

- Does not handle chatbot conversations (delegates to chatbot)
- Does not manage CRM data (delegates to crm)
- Does not execute workflows (delegates to flows)
- Does not process data (delegates to datalab)
