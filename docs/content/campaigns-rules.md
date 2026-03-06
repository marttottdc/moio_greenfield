---
title: "Campaigns Rules & Constraints"
slug: "campaigns-rules"
category: "campaigns"
order: 5
status: "published"
summary: "- Campaign must have `tenant` (tenant-scoped) - Campaign status must be one of: draft, scheduled, active, completed - `sent`, `opened`, `responded` counters must be non-negative - Audience is optional"
tags: ["campaigns"]
---

## Overview

- Campaign must have `tenant` (tenant-scoped) - Campaign status must be one of: draft, scheduled, active, completed - `sent`, `opened`, `responded` counters must be non-negative - Audience is optional

# campaigns - Invariants

## Data Integrity Rules

### Campaign Rules
- Campaign must have `tenant` (tenant-scoped)
- Campaign status must be one of: draft, scheduled, active, completed
- `sent`, `opened`, `responded` counters must be non-negative
- Audience is optional (can run without audience if data_staging provided)

### Audience Rules
- Audience must have `tenant` (tenant-scoped)
- Kind must be one of: STATIC, DYNAMIC
- Manual membership edits only allowed for STATIC audiences
- Size cached and updated on membership changes or rebuilds
- `materialized_at` updated whenever membership is recalculated

### CampaignData Rules
- One-to-one with a message attempt
- Status must be one of: PENDING, SENT, FAILED, SKIPPED
- `sent_at` only populated when status = SENT
- Row locking (select_for_update with skip_locked) prevents duplicate sends

### AudienceMembership Rules
- Unique constraint on (audience, contact)
- `bulk_create` with `ignore_conflicts=True` handles duplicates

## Business Logic Constraints

### Campaign Execution Prerequisites
- `can_launch()` must return True
- Requires: whatsapp_template_id, mapping, data_staging
- Optional: schedule.date for scheduled campaigns

### Message Validation
- Phone number normalized to E.164 format
- Template variables mapped from data staging
- Contact created/updated if `save_contacts=True`

### Rate Limiting
- Batch processing with configurable batch_size (default 100)
- `send_outgoing_messages` task has rate_limit="20/m" (deprecated path)

## Concurrency Controls

### Message Sending
- `select_for_update(skip_locked=True)` prevents race conditions
- Only PENDING status rows are processed
- Atomic counter updates: `Campaign.objects.filter(pk=pk).update(sent=F('sent') + 1)`

### Audience Rebuilding
- `select_for_update` lock on audience during membership updates
- Bulk operations in chunks (CHUNK_SIZE = 1000)
- `transaction.atomic` wrapper for consistency
