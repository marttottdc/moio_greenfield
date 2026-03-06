---
title: "Campaigns Lifecycle"
slug: "campaigns-lifecycle"
category: "campaigns"
order: 3
status: "published"
summary: "- App config registered via `CampaignsConfig` - No explicit ready signals"
tags: ["campaigns"]
---

## Overview

- App config registered via `CampaignsConfig` - No explicit ready signals

# campaigns - Lifecycle

## Startup Behavior

- App config registered via `CampaignsConfig`
- No explicit ready signals

## Runtime Behavior

### Campaign Status Flow

```
DRAFT
  │
  ├── configuration updates
  │   ├── set_audience()
  │   ├── set_template()
  │   ├── set_defaults()
  │   ├── set_mapping()
  │   └── upload data staging
  │
  ├── validate_campaign task
  │
  ▼
SCHEDULED (if schedule.date set)
  │
  ├── celery beat trigger at schedule.date
  │
  ▼
ACTIVE (execute_campaign running)
  │
  ├── CampaignData creation (batched)
  ├── send_outgoing_messages_batch tasks queued
  ├── Messages sent via WhatsApp API
  │
  ▼
COMPLETED (all messages processed)
```

### Campaign Execution Flow

```
execute_campaign(campaign_pk)
  │
  ├── Load campaign and config
  ├── Load CampaignDataStaging.mapped_data
  │
  ├── For each batch (batch_size from config):
  │   ├── Create CampaignData records (bulk_create)
  │   └── Queue send_outgoing_messages_batch task
  │
  ├── Update campaign.status = ACTIVE
  └── Emit "campaign.started" event
```

### Message Sending Flow (send_outgoing_messages_batch)

```
For each item in batch:
  │
  ├── Lock CampaignData row (select_for_update, skip_locked)
  │
  ├── Already processed? → Skip
  │
  ├── ContactService.contact_upsert()
  │   └── Create/update contact if save_contacts=True
  │
  ├── wa.send_outgoing_template()
  │   │
  │   ├── Success:
  │   │   ├── CampaignData.status = SENT
  │   │   ├── CampaignData.sent_at = now()
  │   │   ├── Campaign.sent += 1 (atomic)
  │   │   └── Optionally notify agent
  │   │
  │   └── Failure:
  │       ├── CampaignData.status = FAILED
  │       └── CampaignData.result = error details
  │
  └── close_old_connections() for connection cleanup
```

### Audience Materialization Flow

```
rebuild_dynamic_audience(audience_id)
  │
  ├── Load audience with rules
  ├── evaluate_rules() → desired contact set
  │
  ├── Compare with current membership
  │   ├── to_add = desired - current
  │   └── to_del = current - desired
  │
  ├── bulk_create new AudienceMembership
  ├── delete removed memberships
  │
  └── Update audience.size, audience.materialized_at
```

## Shutdown Behavior

No explicit shutdown behavior. Celery tasks have retry logic for graceful handling.
