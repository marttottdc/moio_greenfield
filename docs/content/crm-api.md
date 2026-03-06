---
title: "Crm API"
slug: "crm-api"
category: "crm"
order: 2
status: "published"
summary: "- `GET /api/v1/contacts/` - List contacts - `POST /api/v1/contacts/` - Create contact - `GET /api/v1/contacts/{id}/` - Get contact detail - `PUT /api/v1/contacts/{id}/` - Update contact - `POST /api/v"
tags: ["crm"]
---

## Overview

- `GET /api/v1/contacts/` - List contacts - `POST /api/v1/contacts/` - Create contact - `GET /api/v1/contacts/{id}/` - Get contact detail - `PUT /api/v1/contacts/{id}/` - Update contact - `POST /api/v

# crm - Interfaces

## Public API Endpoints

### Contacts
- `GET /api/v1/contacts/` - List contacts
- `POST /api/v1/contacts/` - Create contact
- `GET /api/v1/contacts/{id}/` - Get contact detail
- `PUT /api/v1/contacts/{id}/` - Update contact
- `POST /api/v1/contacts/{id}/promote/` - Promote to user

### Tickets
- `GET /api/v1/tickets/` - List tickets
- `POST /api/v1/tickets/` - Create ticket
- `GET /api/v1/tickets/{id}/` - Get ticket detail
- `POST /api/v1/tickets/{id}/comments/` - Add comment

### Deals
- `GET /api/v1/deals/` - List deals
- `POST /api/v1/deals/` - Create deal
- `GET /api/v1/deals/{id}/` - Get deal detail

### Products
- `GET /api/v1/products/` - List products
- `POST /api/v1/products/` - Create product

### Webhooks
- `POST /webhooks/{tenant}/generic/{webhook_id}/` - Generic webhook receiver

## Events Emitted

Via `crm/events/ticket_events.py`:
- Ticket creation events
- Ticket status change events
- Ticket assignment events

## Celery Tasks

### heartbeat
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Health check

### generic_webhook_handler
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Retry**: Max 3 retries, 120s countdown
- **Timeout**: 120s soft limit
- **Input**: `payload`, `headers`, `content_type`, `webhook_id`
- **Side Effects**: Resolves handler, executes, triggers linked flows

### woocommerce_webhook_processor
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Input**: `headers`, `body`, `tenant_code`
- **Handles**: order.created, order.updated, product.created, product.updated

### geocode_branches
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Geocode un-geocoded branches via Google Maps API

### check_dac_deliveries
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Import DAC delivery status

### fetch_frontend_skus_data / import_frontend_skus
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: WooCommerce product import

### fix_order_addresses
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Purpose**: AI-assisted address normalization

### process_received_order
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Purpose**: Full order processing (shipping, fulfillment, invoicing)

## Input/Output Schemas

### ContactSerializer

```python
{
    "user_id": UUID,
    "fullname": str,
    "email": str,
    "phone": str,
    "whatsapp_name": str,
    "source": str,
    "ctype": UUID | None,  # ContactType
    "company": UUID | None,
    "image": str | None,
    "addresses": dict,
    "alt_phone": str,
    "linked_user": UUID | None,
    "created": datetime,
    "updated": datetime
}
```

### TicketSerializer

```python
{
    "id": UUID,
    "subject": str,
    "description": str,
    "status": str,  # "open", "in_progress", "resolved", "closed"
    "priority": str,
    "contact": UUID,
    "assigned_to": UUID | None,
    "origin": str,
    "origin_message_id": str | None,
    "origin_session_id": UUID | None,
    "created": datetime,
    "updated": datetime
}
```

### DealSerializer

```python
{
    "id": UUID,
    "name": str,
    "value": decimal,
    "currency": str,
    "stage": UUID,
    "pipeline": UUID,
    "contact": UUID | None,
    "company": UUID | None,
    "expected_close_date": date | None,
    "comments": str,
    "created": datetime,
    "updated": datetime
}
```

### WebhookConfig

```python
{
    "id": UUID,
    "name": str,
    "handler_path": str,
    "authentication_type": str,  # "bearer", "basic", "hmac_sha256", "jwt"
    "authentication_config": dict,
    "expected_content_type": str,
    "store_payloads": bool,
    "linked_flows": [UUID],
    "locked": bool
}
```
