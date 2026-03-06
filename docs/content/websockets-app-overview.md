---
title: "Websockets App Overview"
slug: "websockets-app-overview"
category: "api-reference"
order: 1
status: "published"
summary: "Real-time event publishing via Django Channels for live updates across the platform (tickets, WhatsApp, campaigns, flows)."
tags: ["websockets_app"]
---

## Overview

Real-time event publishing via Django Channels for live updates across the platform (tickets, WhatsApp, campaigns, flows).

# websockets_app

## Responsibility

Real-time event publishing via Django Channels for live updates across the platform (tickets, WhatsApp, campaigns, flows).

## What it Owns

- No persistent models (stateless event routing)

## Core Components

### WebSocketEventPublisher (`services/publisher.py`)
Central event publishing service:

#### Ticket Events
- `ticket_created()`: New ticket notification
- `ticket_updated()`: Ticket data change
- `ticket_status_changed()`: Status transition
- `ticket_assigned()`: Assignment change
- `ticket_comment_added()`: New comment

#### WhatsApp Events
- `whatsapp_conversation_started()`: Session opened
- `whatsapp_conversation_ended()`: Session closed
- `whatsapp_message_received()`: Incoming message
- `whatsapp_message_sent()`: Outgoing message
- `whatsapp_message_delivered()`: Delivery confirmation
- `whatsapp_message_read()`: Read receipt

#### Campaign Events
- `campaign_stats_updated()`: Live statistics
- `campaign_status_changed()`: Status transition
- `campaign_message_sent()`: Per-message notification
- `campaign_completed()`: Campaign finished

#### Flow Preview Events
- `flow_preview_node_started()`: Node execution start
- `flow_preview_node_finished()`: Node output
- `flow_preview_node_error()`: Node failure
- `flow_preview_completed()`: Run finished

### Consumers (`consumers/`)

#### Base Consumer (`base.py`)
- Tenant authentication
- Group subscription management
- Message routing

#### WhatsApp Consumer (`whatsapp.py`)
- WhatsApp conversation events
- Message updates

#### Tickets Consumer (`tickets.py`)
- Ticket list updates
- Individual ticket changes

#### Flow Preview Consumer (`flow_preview.py`)
- Live flow execution events
- Node-by-node updates

#### Campaigns Consumer (`campaigns.py`)
- Campaign execution monitoring
- Stats updates

#### Desktop CRM Agent (`desktop_crm_agent.py`)
- Desktop application events

## Group Naming Convention

```
tickets_{tenant_id}              - All tenant tickets
ticket_{tenant_id}_{ticket_id}   - Single ticket

whatsapp_{tenant_id}             - All tenant WhatsApp
whatsapp_conv_{tenant_id}_{conv_id} - Single conversation

campaigns_{tenant_id}            - All tenant campaigns
campaign_{tenant_id}_{campaign_id} - Single campaign

flow_preview_{tenant_id}_{flow_id}_{run_id} - Preview run
flow_preview_{tenant_id}_{flow_id}          - All flow previews
```

## Event Structure

```python
{
    "type": "event_type",
    "payload": {...},
    "timestamp": "ISO timestamp"
}
```

## What it Does NOT Do

- Does not persist events (fire-and-forget)
- Does not handle authentication (uses channel layer auth)
- Does not process business logic (just routing)
