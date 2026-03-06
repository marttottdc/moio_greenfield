---
title: "Chatbot Rules & Constraints"
slug: "chatbot-rules"
category: "chatbot"
order: 5
status: "published"
summary: "- Session must have `tenant` (tenant-scoped) - Session linked to Contact via ForeignKey - `active` flag indicates session state - `channel` must be valid: whatsapp, email, instagram, messenger, web - "
tags: ["chatbot"]
---

## Overview

- Session must have `tenant` (tenant-scoped) - Session linked to Contact via ForeignKey - `active` flag indicates session state - `channel` must be valid: whatsapp, email, instagram, messenger, web - 

# chatbot - Invariants

## Data Integrity Rules

### ChatbotSession Rules
- Session must have `tenant` (tenant-scoped)
- Session linked to Contact via ForeignKey
- `active` flag indicates session state
- `channel` must be valid: whatsapp, email, instagram, messenger, web
- `last_interaction` updated on each message

### ChatbotMemory Rules
- Memory belongs to exactly one session
- `author` tracks message sender (user/assistant)
- Messages ordered by creation timestamp

### AgentConfiguration Rules
- Agent name unique per tenant
- `channel` determines which sessions use this agent
- `model_settings` contains LLM configuration

### WaMessageLog Rules
- `msg_id` from WhatsApp API for correlation
- `status` tracks delivery: sent, delivered, read, failed
- `timestamp` from WhatsApp for accurate timing

### TenantToolConfiguration Rules
- One record per (tenant, tool_name) combination
- `enabled` flag controls tool availability
- `custom_description` overrides default tool description

## Business Logic Constraints

### Conversation Handler Selection
- `TenantConfiguration.conversation_handler` determines routing:
  - `CHATBOT`: Legacy GPT-based handler
  - `ASSISTANT`: OpenAI Assistants API
  - `AGENT`: MoioAgent with tools

### Message Processing Prerequisites
- TenantConfiguration must exist with matching WABA ID and Phone ID
- `whatsapp_integration_enabled` must be True
- Valid OpenAI API key for AI processing

### Media Processing
- Audio: Transcribed via Whisper API
- Images: Described via GPT-4 Vision
- Documents: Logged but not processed
- Videos: Logged but not processed

## Concurrency Controls

### Webhook Processing
- Tasks queued to Celery for async processing
- Task retries with exponential backoff
- Database connections closed between operations

### Session State
- `pre_save` signal captures previous state
- `post_save` compares for transition detection
- Atomic operations for session updates
