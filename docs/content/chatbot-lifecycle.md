---
title: "Chatbot Lifecycle"
slug: "chatbot-lifecycle"
category: "chatbot"
order: 3
status: "published"
summary: "- Imports signals module on app ready - Signal: `sync_tools_for_new_tenant` registered for new tenant creation - Schedules tool sync via Celery on tenant creation"
tags: ["chatbot"]
---

## Overview

- Imports signals module on app ready - Signal: `sync_tools_for_new_tenant` registered for new tenant creation - Schedules tool sync via Celery on tenant creation

# chatbot - Lifecycle

## Startup Behavior

- Imports signals module on app ready
- Signal: `sync_tools_for_new_tenant` registered for new tenant creation
- Schedules tool sync via Celery on tenant creation

## Runtime Behavior

### WhatsApp Message Processing Flow

```
whatsapp_webhook_handler(body)
  │
  ├── Parse WhatsappWebhook
  ├── Determine webhook_type (messages, statuses)
  │
  ├── Store WaPayloads record
  │
  ├── Find TenantConfiguration by WABA ID + Phone ID
  │   └── Not found? → Forward to redirect URL
  │
  ├── Based on conversation_handler:
  │   │
  │   ├── CHATBOT:
  │   │   └── process_message_with_chatbot()
  │   │       ├── Get/create contact
  │   │       ├── Create Chatbot instance
  │   │       ├── Process message by type
  │   │       └── Send reply via Messenger
  │   │
  │   ├── ASSISTANT:
  │   │   └── process_message_with_assistant()
  │   │       ├── Get/create contact
  │   │       ├── Create MoioAssistant (OpenAI)
  │   │       ├── Process with Whisper/Vision if needed
  │   │       ├── Get AI response
  │   │       └── Send via smart_reply or structured_reply
  │   │
  │   └── AGENT:
  │       └── process_message_with_agent()
  │           ├── Get/create contact
  │           ├── Create AgentEngine
  │           ├── Preprocess message
  │           ├── reply_to_message()
  │           └── Send via just_reply()
  │
  └── Register message in WaMessageLog
```

### Session Lifecycle

```
Signal: pre_save(ChatbotSession)
  └── Capture previous state for transition detection

Signal: post_save(ChatbotSession)
  │
  ├── If created:
  │   └── chatbot_events.session_started()
  │       ├── Emit communications.session_started event
  │       └── WebSocket: whatsapp_conversation_started
  │
  └── If active changed to False:
      └── chatbot_events.session_ended()
          ├── Emit communications.session_ended event
          ├── WebSocket: whatsapp_conversation_ended
          └── Send email notification to default_notification_list
```

### Session Sweeper Flow

```
session_sweeper() [Celery beat]
  │
  ├── For each WhatsApp-enabled tenant:
  │   │
  │   └── For each active WhatsApp session:
  │       │
  │       ├── Check has_time_passed(last_interaction, inactivity_limit)
  │       │
  │       └── If inactive:
  │           ├── AgentEngine.analyze_conversation()
  │           └── Send closing message
```

### Tool Synchronization

```
Tenant created (post_save signal)
  │
  └── Schedule sync_single_tenant_tools_task (countdown=2s)
      │
      └── For each available tool:
          └── TenantToolConfiguration.get_or_create()
```

## Shutdown Behavior

- No explicit shutdown behavior
- Celery tasks have retry logic for graceful handling
- WebSocket connections managed by Django Channels
