---
title: "Crm Rules & Constraints"
slug: "crm-rules"
category: "crm"
order: 5
status: "published"
summary: "- Contact must have `tenant` (tenant-scoped) - Phone unique per tenant (when not null) - Email unique per tenant (when not null) - `embedding` generated from contact data for similarity search"
tags: ["crm"]
---

## Overview

- Contact must have `tenant` (tenant-scoped) - Phone unique per tenant (when not null) - Email unique per tenant (when not null) - `embedding` generated from contact data for similarity search

# crm - Invariants

## Data Integrity Rules

### Contact Rules
- Contact must have `tenant` (tenant-scoped)
- Phone unique per tenant (when not null)
- Email unique per tenant (when not null)
- `embedding` generated from contact data for similarity search

### ContactType Rules
- ContactType must have `tenant` (tenant-scoped)
- Name unique per tenant (implicit)

### Company Rules
- Company must have `tenant` (tenant-scoped)
- `external_id` for external system correlation

### Branch Rules
- Branch must have `tenant` (tenant-scoped)
- Geocoding performed async via task
- `geocoded` flag tracks geocoding status

### Ticket Rules
- Ticket must have `tenant` (tenant-scoped)
- Status must be valid: open, in_progress, resolved, closed
- Origin tracks source: whatsapp, email, web, manual

### Deal Rules
- Deal must have `tenant` (tenant-scoped)
- Must belong to a DealPipeline via DealStage
- Value must be non-negative

### Product Rules
- Product must have `tenant` (tenant-scoped)
- SKU should be unique per tenant (enforced via index)
- `embedding` generated for similarity search

### WebhookConfig Rules
- WebhookConfig must have `tenant` (tenant-scoped)
- Authentication type must be valid: bearer, basic, hmac_sha256, jwt
- `locked` flag prevents deletion/modification

## Business Logic Constraints

### Contact Upsert
- Phone is primary lookup key
- Updates existing if phone matches
- Creates new if no match

### User Promotion
- Requires email on contact
- Email must not exist in MoioUser table
- Creates linked MoioUser with contact data

### Contact–MoioUser Sync (portal/signals.py)
- `create_internal_contact` runs on `post_save(MoioUser)` (including on login when `last_login` is updated)
- Lookup must use **priority order**: linked_user → email → phone (only when non-empty)
- Do NOT match by empty email/phone: they match many rows; `.first()` can return the wrong contact, and updating it with the user’s email violates `unique_email_tenant`

### Webhook Handler Resolution
- First tries registry lookup by handler_path
- Falls back to dotted import
- Falls back to "default_handler"
