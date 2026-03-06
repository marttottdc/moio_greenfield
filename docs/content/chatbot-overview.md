---
title: "Chatbot Overview"
slug: "chatbot-overview"
category: "chatbot"
order: 1
status: "published"
summary: "AI-powered conversational agents with multi-channel support (WhatsApp, Instagram, Messenger, Email) and real-time session management."
tags: ["chatbot"]
---

## Overview

AI-powered conversational agents with multi-channel support (WhatsApp, Instagram, Messenger, Email) and real-time session management.

# chatbot

## Responsibility

AI-powered conversational agents with multi-channel support (WhatsApp, Instagram, Messenger, Email) and real-time session management.

## What it Owns

- **ChatbotSession**: Conversation sessions with contacts (channel, status, context)
- **ChatbotMemory**: Message history within sessions
- **AgentConfiguration**: AI agent definitions (model, tools, prompts, channels)
- **TenantToolConfiguration**: Per-tenant tool enablement and customization
- **ChatbotConfiguration**: Legacy chatbot configuration (deprecated)
- **WaMessageLog**: WhatsApp message delivery status tracking
- **WaPayloads**: Raw webhook payload storage for debugging
- **WaTemplates**: WhatsApp template management
- **EmailAccount/EmailMessage**: Email channel integration

## Core Components

### Conversation Handlers

#### MoioAgent (`core/moio_agent.py`)
Primary agent engine for conversations:
- `AgentEngine`: Wraps agent with session management
- `reply_to_message()`: Process incoming message with agent
- `analyze_conversation()`: Run agent analysis on session
- `register_outgoing_campaign_message()`: Track outbound campaign messages

#### Chatbot (`core/chatbot.py`)
Legacy chatbot handler:
- `Chatbot`: Simple GPT-based responder
- `MoioAssistant`: OpenAI Assistants API integration

#### Messenger (`core/messenger.py`)
Multi-channel message sending:
- `just_reply()`: Plain text reply
- `smart_reply()`: Structured message formatting
- `structured_reply()`: JSON schema formatted reply
- `reply_email()`: Email channel reply

### Webhook Processors

#### Message Preprocessing (`tasks.py:preprocess_message()`)
Normalizes incoming WhatsApp content:
- Text extraction
- Audio transcription via Whisper
- Image description via GPT-4 Vision
- Location parsing
- Interactive content extraction

#### Conversation Handler Routing
Based on `TenantConfiguration.conversation_handler`:
- `CHATBOT`: `process_message_with_chatbot()`
- `ASSISTANT`: `process_message_with_assistant()`
- `AGENT`: `process_message_with_agent()`

### Tool Registry (`tools_registry.py`)
Agent tool definitions and discovery:
- Platform tools (CRM, calendar, flows)
- Custom tenant tools
- Tool parameter schemas

## What it Does NOT Do

- Does not manage contacts (delegates to crm)
- Does not handle authentication (delegates to portal)
- Does not execute flows directly (delegates to flows)
- Does not manage campaigns (delegates to campaigns)
