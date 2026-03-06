---
title: "Campaigns Error Handling"
slug: "campaigns-errors"
category: "campaigns"
order: 6
status: "published"
summary: "- Returns empty list if campaign not found - Returns empty list if data_staging not found or empty - Event emission wrapped in try/except (non-blocking)"
tags: ["campaigns"]
---

## Overview

- Returns empty list if campaign not found - Returns empty list if data_staging not found or empty - Event emission wrapped in try/except (non-blocking)

# campaigns - Failures

## Explicit Error Handling

### execute_campaign
- Returns empty list if campaign not found
- Returns empty list if data_staging not found or empty
- Event emission wrapped in try/except (non-blocking)

### validate_campaign
- Returns None if campaign not found
- Returns None if whatsapp_template_id not configured
- Returns None if data_staging not found
- Counts errors during message validation (incremental error counter)

### send_outgoing_messages_batch
- **Celery retry**: Auto-retry on `OperationalError` with backoff (max 5 retries)
- Row lock failed (DoesNotExist): Marks item as "skipped"
- Contact upsert failure: Marks CampaignData as SKIPPED with error details
- Message send failure: Marks CampaignData as FAILED, continues to next
- Unexpected exceptions: Logs error, adds to failed count, continues

### send_outgoing_messages (deprecated)
- Rate limited to 20/m
- Auto-retry on `OperationalError` with jitter
- Max 5 retries with exponential backoff

### Audience Operations
- `_enforce_static()`: Raises `ValidationError` for non-STATIC audience edits
- `rebuild_dynamic_audience()`: Raises `ValidationError` for non-DYNAMIC audiences

## Expected Failure Modes

### WhatsApp API Failures
- Template not found
- Invalid phone number format
- Rate limiting from WhatsApp
- Network timeouts

### Database Failures
- Connection errors (handled by `close_old_connections()` calls)
- Lock timeouts (handled by `skip_locked` parameter)
- Transaction deadlocks (Celery retry mechanism)

### Data Validation Failures
- Invalid template variable mapping
- Missing required fields
- Phone number normalization failures

## Recovery Mechanisms

### Automatic Recovery
- Celery task retries with exponential backoff
- Database connection cleanup between messages
- Skip-locked pattern prevents duplicate processing

### Manual Recovery
- Re-launch campaign (creates new CampaignData for pending records)
- Check `CampaignData.result` for error details
- Review `log_campaign_activity()` for delivery status

### Idempotency
- CampaignData status check before processing
- Skip already processed items
- Atomic counter updates prevent over-counting
