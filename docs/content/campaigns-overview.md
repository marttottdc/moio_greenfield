---
title: "Campaigns Overview"
slug: "campaigns-overview"
category: "campaigns"
order: 1
status: "published"
summary: "Marketing campaign management with audience targeting, WhatsApp template messaging, and campaign execution orchestration."
tags: ["campaigns"]
---

## Overview

Marketing campaign management with audience targeting, WhatsApp template messaging, and campaign execution orchestration.

# campaigns

## Responsibility

Marketing campaign management with audience targeting, WhatsApp template messaging, and campaign execution orchestration.

## What it Owns

- **Campaign**: Campaign definitions with channel, status, configuration, audience linkage
- **Audience**: Target audience definitions (static or dynamic with rules)
- **AudienceMembership**: Contact-audience linkage with snapshot data
- **CampaignData**: Per-message tracking with variables, status, results
- **CampaignDataStaging**: Temporary data staging during campaign configuration

## Core Components

### Campaign Engine (`core/campaigns_engine.py`)
- `whatsapp_message_validator()`: Validates messages against template requirements
- `whatsapp_message_generator()`: Generates WhatsApp payloads from templates
- `contact_validator()`: Validates and normalizes contact data
- `sanitize_key()`: Normalizes template variable keys

### Campaign Service (`core/service.py`)
Audience and campaign management:
- `add_static_contacts()`: Bulk add contacts to static audience
- `remove_static_contacts()`: Remove contacts from static audience
- `rebuild_dynamic_audience()`: Materialize dynamic audience from rules
- `launch_campaign()`: Queue campaign for execution
- `queue_campaign_validation()`: Validate campaign configuration
- `clone_campaign()`: Clone campaign configuration
- `update_template()`, `update_defaults()`, `update_schedule()`: Configuration updates
- `log_campaign_activity()`: Retrieve campaign message delivery logs

### Campaign Tasks (`tasks.py`)
- `execute_campaign`: Main campaign execution orchestrator (chunked batch processing)
- `validate_campaign`: Pre-execution validation and data mapping
- `send_outgoing_messages_batch`: Batch message sending with retry logic
- `send_outgoing_messages`: Individual message sending (deprecated, rate-limited)

### Audience AI (`core/audience_ai/`)
- `llm.py`: LLM-based audience rule generation
- `qtranslate.py`: Rule translation to ORM queries
- `audience_rules.py`: Rule evaluation engine

## What it Does NOT Do

- Does not manage contacts directly (delegates to crm)
- Does not send messages directly (uses chatbot WhatsApp client)
- Does not store contact data (references crm.Contact)
- Does not handle authentication (delegates to portal)
