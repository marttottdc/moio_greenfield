---
title: "Chatbot API"
slug: "chatbot-api"
category: "chatbot"
order: 2
status: "published"
summary: "- `POST /webhooks/whatsapp/` - WhatsApp webhook receiver - `POST /webhooks/instagram/` - Instagram webhook receiver - `POST /webhooks/messenger/` - Messenger webhook receiver"
tags: ["chatbot"]
---

## Overview

- `POST /webhooks/whatsapp/` - WhatsApp webhook receiver - `POST /webhooks/instagram/` - Instagram webhook receiver - `POST /webhooks/messenger/` - Messenger webhook receiver

# chatbot - Interfaces

## Public Endpoints

### Webhooks (External)
- `POST /webhooks/whatsapp/` - WhatsApp webhook receiver
- `POST /webhooks/instagram/` - Instagram webhook receiver
- `POST /webhooks/messenger/` - Messenger webhook receiver

### API Endpoints
- `GET /api/v1/chatbot/sessions/` - List sessions
- `GET /api/v1/chatbot/sessions/{id}/` - Get session detail
- `GET /api/v1/chatbot/agents/` - List agent configurations
- `POST /api/v1/chatbot/agents/` - Create agent
- `GET /api/v1/chatbot/tenant-tools/` - List tenant tool configurations

## Events Emitted

### communications.session_started
Emitted when a chatbot session is created.

```python
{
    "name": "communications.session_started",
    "tenant_id": str,
    "entity": {"type": "chatbot_session", "id": str},
    "payload": {
        "session_id": str,
        "contact_id": str | None,
        "channel": str,
        "started_at": str,
        "active": bool,
        "context": dict,
        "contact": dict,
        "session": dict  # Full session snapshot
    },
    "source": "chatbot"
}
```

### communications.session_ended
Emitted when a chatbot session ends.

```python
{
    "name": "communications.session_ended",
    "tenant_id": str,
    "entity": {"type": "chatbot_session", "id": str},
    "payload": {
        "session_id": str,
        "contact_id": str | None,
        "channel": str,
        "started_at": str,
        "ended_at": str,
        "active": bool,
        "context": dict,
        "final_summary": str | None,
        "csat": float | None,
        "messages_count": int,
        "messages": list,
        "contact": dict,
        "session": dict
    },
    "source": "chatbot"
}
```

## WebSocket Events

### whatsapp_conversation_started
Via `WebSocketEventPublisher`:
- `tenant_id`, `conversation_id`, `conversation_data`

### whatsapp_conversation_ended
Via `WebSocketEventPublisher`:
- `tenant_id`, `conversation_id`, `conversation_data`

### whatsapp_message_received / whatsapp_message_sent
Via `WebSocketEventPublisher`:
- `tenant_id`, `conversation_id`, `message_data`

## Celery Tasks

### whatsapp_webhook_handler
- **Queue**: `HIGH_PRIORITY_Q`
- **Retry**: Max 5 retries, 10s countdown, exponential backoff
- **Input**: `body: dict` (webhook payload)
- **Side Effects**: Creates contacts, processes messages, sends replies

### instagram_webhook_handler
- **Queue**: `HIGH_PRIORITY_Q`
- **Retry**: Max 5 retries, 10s countdown, exponential backoff
- **Input**: `body: dict`

### messenger_webhook_handler
- **Queue**: `HIGH_PRIORITY_Q`
- **Retry**: Max 5 retries, 10s countdown, exponential backoff
- **Input**: `body: dict`

### session_sweeper
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Purpose**: Close inactive sessions based on `assistants_inactivity_limit`

### archive_conversation
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Input**: `session_id: str`
- **Side Effects**: Sends closing message, archives session

### sync_tenant_tools_task
- **Queue**: `HIGH_PRIORITY_Q`
- **Retry**: Max 5 retries, exponential backoff to 300s
- **Purpose**: Sync available tools to all tenant configurations

### sync_email_account_task / sync_all_email_accounts
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Email account synchronization

## Input/Output Schemas

### Preprocessed Message

```python
{
    "content": str,
    "type": str,  # Content type
    "read": bool,
    "error": bool,
    "msg_id": str,
    "original_content": dict,
    "context": str,  # JSON string of reply context
    "media": str | None  # Media path/URL
}
```

### Agent Configuration

```python
{
    "id": UUID,
    "name": str,
    "tenant": UUID,
    "channel": str,  # "whatsapp", "email", etc.
    "model_settings": {
        "model": str,
        "temperature": float
    },
    "options": dict,
    "enable_websearch": bool
}
```

### WhatsApp Webhook Types
- `messages`: Incoming message
- `statuses`: Delivery status update (sent, delivered, read, failed)
