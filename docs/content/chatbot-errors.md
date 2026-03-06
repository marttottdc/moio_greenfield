---
title: "Chatbot Error Handling"
slug: "chatbot-errors"
category: "chatbot"
order: 6
status: "published"
summary: "- **ImproperlyConfigured**: No PortalConfiguration - **TenantConfiguration.DoesNotExist**: Forward to redirect URL - **TenantConfiguration.MultipleObjectsReturned**: Raise ValueError - **Parse errors*"
tags: ["chatbot"]
---

## Overview

- **ImproperlyConfigured**: No PortalConfiguration - **TenantConfiguration.DoesNotExist**: Forward to redirect URL - **TenantConfiguration.MultipleObjectsReturned**: Raise ValueError - **Parse errors*

# chatbot - Failures

## Explicit Error Handling

### whatsapp_webhook_handler
- **ImproperlyConfigured**: No PortalConfiguration
- **TenantConfiguration.DoesNotExist**: Forward to redirect URL
- **TenantConfiguration.MultipleObjectsReturned**: Raise ValueError
- **Parse errors**: Log exception, set status to "parse_error"
- **General exceptions**: Celery retry with backoff

### Message Preprocessing
- **Audio transcription failure**: Returns error flag, fallback message
- **Image description failure**: Returns error flag, continues processing
- **Document/Video**: Sets error flag (not supported)

### Agent Processing
- **Agent response None**: Sets reply to "Error"
- **Reply not string**: Converts via `model_dump()`

### Session Sweeper
- **Per-session exceptions**: Logged but don't stop sweep
- Continues to next session on any error

### Tool Sync
- **Tool sync failure**: Logged, task retries
- **Import errors**: Logged as warning, tool skipped

## Expected Failure Modes

### WhatsApp API Failures
- Message download failures (media)
- Mark-as-read failures
- Message send failures
- Rate limiting

### AI API Failures
- OpenAI API errors (rate limits, timeouts)
- Whisper transcription failures
- Vision API failures
- Token limit exceeded

### Database Failures
- Connection errors
- Session not found
- Contact creation failures

## Recovery Mechanisms

### Automatic Recovery
- Celery task retries (max 5, exponential backoff)
- `close_old_connections()` for connection cleanup
- Error flag in message prevents processing loops

### Webhook Forwarding
- Unknown tenant → Forward to `whatsapp_webhook_redirect`
- Parsing error → Forward to redirect URL
- Preserves payload for external processing

### Fallback Responses
- Audio failure: "No entendí el mensaje, me podrías escribir el mensaje?"
- Video failure: "No puedo entender videos aun, me podrías escribir el mensaje?"
- Unknown type: "no se interpretar {type}, me lo puedes escribir?"

### Signal Error Handling
- Event emission wrapped in try/except (non-blocking)
- Session end notification failures don't break session
- Cache read logging for debugging
