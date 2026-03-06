---
title: "Portal API"
slug: "portal-api"
category: "integrations"
order: 2
status: "published"
summary: "- `POST /api/token/` - Obtain JWT tokens - `POST /api/token/refresh/` - Refresh JWT token - `/accounts/` - allauth authentication routes"
tags: ["portal"]
---

## Overview

- `POST /api/token/` - Obtain JWT tokens - `POST /api/token/refresh/` - Refresh JWT token - `/accounts/` - allauth authentication routes

# portal - Interfaces

## Public API Endpoints

### Authentication
- `POST /api/token/` - Obtain JWT tokens
- `POST /api/token/refresh/` - Refresh JWT token
- `/accounts/` - allauth authentication routes

### Integrations
- `GET /api/v1/integrations/accounts/` - List external accounts
- `POST /api/v1/integrations/accounts/` - Connect account
- `POST /api/v1/integrations/accounts/{id}/sync/` - Trigger sync

### Email Integration
- `GET /api/v1/integrations/email/messages/` - List emails
- `POST /api/v1/integrations/email/send/` - Send email

### Calendar Integration
- `GET /api/v1/integrations/calendar/events/` - List events
- `POST /api/v1/integrations/calendar/events/` - Create event

## Celery Tasks

### email_ingest
- **Queue**: Default
- **Purpose**: Sync emails from connected accounts
- **Source**: `portal.integrations.v1.tasks.email`

### calendar_ingest
- **Queue**: Default
- **Purpose**: Sync calendar events from connected accounts
- **Source**: `portal.integrations.v1.tasks.calendar`

## Events Emitted

None directly. Portal provides infrastructure for other apps to emit events.

## Input/Output Schemas

### TenantConfiguration

```python
{
    "tenant": UUID,
    
    # WhatsApp Integration
    "whatsapp_integration_enabled": bool,
    "whatsapp_business_account_id": str,
    "whatsapp_phone_id": str,
    "whatsapp_token": str,
    "whatsapp_name": str,
    "whatsapp_catalog_id": str,
    
    # OpenAI Integration
    "openai_integration_enabled": bool,
    "openai_api_key": str,
    "openai_default_model": str,
    "openai_embedding_model": str,
    
    # Assistants
    "assistants_enabled": bool,
    "assistants_default_id": str,
    "assistants_inactivity_limit": int,
    "assistant_smart_reply_enabled": bool,
    "assistant_output_formatting_instructions": str,
    
    # Conversation Handler
    "conversation_handler": str,  # "chatbot", "assistant", "agent"
    "chatbot_enabled": bool,
    
    # Agent Settings
    "agent_allow_reopen_session": bool,
    
    # Google Integration
    "google_integration_enabled": bool,
    "google_api_key": str,
    
    # WooCommerce Integration
    "woocommerce_integration_enabled": bool,
    "woocommerce_site_url": str,
    "woocommerce_consumer_key": str,
    "woocommerce_consumer_secret": str,
    
    # MercadoPago Integration
    "mercadopago_access_token": str,
    "mercadopago_client_id": str,
    "mercadopago_client_secret": str,
    
    # WordPress Integration
    "wordpress_site_url": str,
    "wordpress_app_password": str,
    
    # Psigma Integration
    "psigma_integration_enabled": bool,
    "psigma_user": str,
    "psigma_password": str,
    "psigma_token": str,
    
    # DAC Integration
    "dac_notification_list": str,
    
    # SMTP Settings
    "smtp_from": str,
    "smtp_host": str,
    "smtp_user": str,
    "smtp_password": str,
    
    # Notifications
    "default_notification_list": str  # Comma-separated emails
}
```

### MoioUser

```python
{
    "id": UUID,
    "email": str,
    "username": str,
    "first_name": str,
    "last_name": str,
    "phone": str,
    "tenant": UUID,
    "preferences": dict,
    "is_active": bool,
    "date_joined": datetime
}
```

### Tenant

```python
{
    "id": UUID,
    "tenant_code": str,  # Unique identifier
    "nombre": str,  # Display name
    "subdomain": str,
    "plan": str,
    "created": datetime
}
```

### ContentBlock

```python
{
    "id": UUID,
    "tenant": UUID,
    "template": UUID,  # ComponentTemplate
    "name": str,
    "content": dict,
    "visibility": str,
    "created": datetime,
    "updated": datetime
}
```

### ExternalAccount

```python
{
    "id": UUID,
    "tenant": UUID,
    "owner": UUID,  # MoioUser
    "provider": str,  # "google", "microsoft", "imap"
    "email": str,
    "access_token": str,
    "refresh_token": str,
    "token_expires_at": datetime,
    "sync_enabled": bool,
    "last_synced_at": datetime
}
```
