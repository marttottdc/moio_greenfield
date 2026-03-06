---
title: "Campaigns API"
slug: "campaigns-api"
category: "campaigns"
order: 2
status: "published"
summary: "- `GET /api/v1/campaigns/` - List campaigns - `POST /api/v1/campaigns/` - Create campaign - `GET /api/v1/campaigns/{id}/` - Get campaign detail - `PUT /api/v1/campaigns/{id}/` - Update campaign - `DEL"
tags: ["campaigns"]
---

## Overview

- `GET /api/v1/campaigns/` - List campaigns - `POST /api/v1/campaigns/` - Create campaign - `GET /api/v1/campaigns/{id}/` - Get campaign detail - `PUT /api/v1/campaigns/{id}/` - Update campaign - `DEL

# campaigns - Interfaces

## Public API Endpoints

### Campaign CRUD
- `GET /api/v1/campaigns/` - List campaigns
- `POST /api/v1/campaigns/` - Create campaign
- `GET /api/v1/campaigns/{id}/` - Get campaign detail
- `PUT /api/v1/campaigns/{id}/` - Update campaign
- `DELETE /api/v1/campaigns/{id}/` - Delete campaign

### Campaign Configuration
- `POST /api/v1/campaigns/{id}/set-audience/` - Link audience to campaign
- `POST /api/v1/campaigns/{id}/set-template/` - Set WhatsApp template
- `POST /api/v1/campaigns/{id}/set-defaults/` - Set default configuration
- `POST /api/v1/campaigns/{id}/set-mapping/` - Set data field mapping
- `POST /api/v1/campaigns/{id}/clone/` - Clone campaign

### Campaign Execution
- `POST /api/v1/campaigns/{id}/launch/` - Execute campaign
- `POST /api/v1/campaigns/{id}/validate/` - Validate campaign
- `GET /api/v1/campaigns/{id}/activity/` - Get delivery logs

### Audience CRUD
- `GET /api/v1/audiences/` - List audiences
- `POST /api/v1/audiences/` - Create audience
- `GET /api/v1/audiences/{id}/` - Get audience detail
- `POST /api/v1/audiences/{id}/contacts/` - Add/remove static contacts
- `POST /api/v1/audiences/{id}/rebuild/` - Rebuild dynamic audience

## Events Emitted

### campaign.started
Emitted when campaign execution begins.

```python
{
    "name": "campaign.started",
    "tenant_id": str,
    "entity": {"type": "campaign", "id": str},
    "payload": {
        "campaign_id": str,
        "name": str,
        "channel": str,
        "kind": str,
        "status": str,
        "audience_id": str | None,
        "audience_name": str | None,
        "audience_size": int | None,
        "job_ids": [str],
        "started_at": str  # ISO timestamp
    },
    "source": "task"
}
```

## Events Consumed

None explicitly visible in code.

## Input/Output Schemas

### CampaignSerializer

```python
{
    "id": UUID,
    "name": str,
    "description": str,
    "channel": str,  # "whatsapp", "email", etc.
    "kind": str,  # "outbound", "reminder", etc.
    "status": str,  # "draft", "scheduled", "active", "completed"
    "sent": int,
    "opened": int,
    "responded": int,
    "audience": UUID | None,
    "audience_name": str,  # read-only
    "audience_size": int,  # read-only
    "open_rate": float,  # read-only, calculated
    "ready_to_launch": bool,  # read-only
    "created": datetime,
    "updated": datetime
}
```

### CampaignConfigSerializer

```python
{
    "message": {
        "whatsapp_template_id": str,
        "map": [
            {
                "template_var": str,
                "target_field": str,
                "type": "variable" | "fixed_value",
                "template_element": str  # "header", "body", etc.
            }
        ]
    },
    "defaults": {
        "auto_correct": bool,
        "use_first_name": bool,
        "save_contacts": bool,
        "notify_agent": bool,
        "contact_type": str,
        "country_code": str
    },
    "data": {
        "data_staging": UUID
    },
    "schedule": {
        "date": datetime | None
    }
}
```

### AudienceSerializer

```python
{
    "id": UUID,
    "name": str,
    "description": str,
    "kind": str,  # "STATIC" | "DYNAMIC"
    "size": int,
    "is_draft": bool,
    "materialized_at": datetime | None,
    "rules": dict | None,  # For DYNAMIC audiences
    "created": datetime,
    "updated": datetime
}
```

### AudienceRulesSerializer

```python
{
    "and_rules": [
        {
            "field": str,
            "op": str,  # "eq", "ne", "gt", "lt", etc.
            "value": any,
            "value_to": any | None,  # For range operators
            "negate": bool
        }
    ],
    "or_rules": [...]
}
```

## Celery Tasks

### execute_campaign
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Input**: `campaign_pk: str`
- **Output**: `List[str]` (job IDs)
- **Side Effects**: Creates CampaignData records, queues send batches

### validate_campaign
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Input**: `campaign_pk: str`
- **Output**: `List[dict]` (mapped message data)
- **Side Effects**: Validates template, maps data staging

### send_outgoing_messages_batch
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Rate Limit**: None (batch handles concurrency)
- **Input**: `batch: List[str]`, `campaign_pk: str`
- **Output**: Summary dict with sent/failed counts
- **Retry**: Auto-retry on OperationalError, max 5 retries

### rebuild_dynamic_audience
- **Queue**: Default
- **Input**: `audience_id: UUID`
- **Side Effects**: Materializes audience membership from rules
