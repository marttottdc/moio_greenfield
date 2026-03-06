---
title: "Crm Lifecycle"
slug: "crm-lifecycle"
category: "crm"
order: 3
status: "published"
summary: "- App config registered via `CrmConfig` - Signals imported on ready (minimal signal handlers)"
tags: ["crm"]
---

## Overview

- App config registered via `CrmConfig` - Signals imported on ready (minimal signal handlers)

# crm - Lifecycle

## Startup Behavior

- App config registered via `CrmConfig`
- Signals imported on ready (minimal signal handlers)

## Runtime Behavior

### Contact Creation Flow

```
ContactService.create_contact()
  │
  ├── Validate required fields (fullname, phone)
  │
  ├── transaction.atomic():
  │   │
  │   ├── Get/create ContactType if specified
  │   │
  │   └── Contact.create_or_update()
  │       ├── Normalize phone number
  │       ├── Check existing by phone
  │       └── Create or update record
  │
  └── Return (contact, message)
```

### Contact to User Promotion

```
ContactService.promote_contact_to_user()
  │
  ├── Validate contact exists
  ├── Validate not already linked to user
  ├── Validate has email
  ├── Check email not taken
  ├── Check username not taken
  │
  └── transaction.atomic():
      │
      ├── MoioUser.objects.create_user()
      │
      ├── ContactType.get_or_create("User")
      │
      └── Update contact (linked_user, ctype)
```

### Webhook Processing Flow

```
generic_webhook_handler(payload, headers, content_type, webhook_id)
  │
  ├── Load WebhookConfig
  │   └── Not found? → Return "No Handler Configured"
  │
  ├── Store payload if store_payloads=True
  │
  ├── Resolve handler:
  │   ├── From handler_path (registry or dotted import)
  │   └── Fallback to "default_handler"
  │
  ├── Execute handler(payload, headers, content_type, config)
  │
  └── Return handler result
```

### WooCommerce Integration Flow

```
woocommerce_webhook_processor(headers, body, tenant_code)
  │
  ├── Parse headers and payload
  │
  ├── Based on topic:
  │   │
  │   ├── order.created / order.updated:
  │   │   └── register_or_update_ecommerce_order()
  │   │
  │   └── product.created / product.updated:
  │       └── import_woo_product()
```

### Order Processing Flow

```
process_received_order(order_number)
  │
  ├── Load EcommerceOrder
  │
  ├── register_shipping_request()
  │
  ├── create_dac_delivery() → tracking_code
  │
  ├── send_order_to_dac_fulfillment()
  │
  ├── get_customer_code()
  │
  ├── send_woocommerce_order_to_zeta() [Invoice]
  │
  └── send_tracking_code_to_user()
```

## Shutdown Behavior

No explicit shutdown behavior. Celery tasks have retry logic.
