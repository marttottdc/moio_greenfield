---
title: "Crm Overview"
slug: "crm-overview"
category: "crm"
order: 1
status: "published"
summary: "Customer relationship management with contacts, tickets, deals, pipelines, products, knowledge base, and webhook integrations."
tags: ["crm"]
---

## Overview

Customer relationship management with contacts, tickets, deals, pipelines, products, knowledge base, and webhook integrations.

# crm

## Responsibility

Customer relationship management with contacts, tickets, deals, pipelines, products, knowledge base, and webhook integrations.

## What it Owns

- **Contact**: Customer/lead records with phone, email, embedding, image
- **ContactType**: Contact categorization per tenant
- **Company/Branch/Address**: Business location management
- **Ticket/TicketComment**: Support ticket tracking
- **Deal/DealPipeline/DealStage**: Sales pipeline management
- **Product/ProductVariant/Stock**: Product catalog with variants
- **Tag**: Tagging system with embeddings
- **KnowledgeItem**: Knowledge base entries
- **ActivityRecord/ActivityType**: Activity logging
- **WebhookConfig/WebhookPayload**: External webhook management
- **EcommerceOrder/Shipment**: E-commerce integration
- **Face/FaceDetection**: Face recognition data

## Core Components

### Contact Service (`services/contact_service.py`)
- `create_contact()`: Contact creation with type assignment
- `contact_upsert()`: Create or update by phone
- `promote_contact_to_user()`: Convert contact to MoioUser
- `search_contacts()`: Contact search
- `list_contacts()`: Tenant-filtered listing

### Ticket Service (`services/ticket_service.py`)
- Ticket creation and updates
- Status transitions
- Comment management

### Activity Service (`services/activity_service.py`)
- Activity logging
- Activity type management

### Webhook Handlers
- `generic_webhook_handler`: Celery task for all webhooks
- Handler resolution via registry or dotted path
- Payload storage option
- Retry logic with backoff

### WooCommerce Integration
- `woocommerce_webhook_processor`: Order/product sync
- `import_woo_product()`: Product import
- `register_or_update_ecommerce_order()`: Order sync

### Contracts System (`contracts/`)
- `ContactContract`: Contact operations interface
- `TicketContract`: Ticket operations interface
- `DealContract`: Deal operations interface
- `AudienceContract`: Audience query interface

## What it Does NOT Do

- Does not handle authentication (delegates to portal)
- Does not send messages (delegates to chatbot)
- Does not manage campaigns (delegates to campaigns)
- Does not execute workflows (delegates to flows)
