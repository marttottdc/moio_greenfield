---
title: "Campaigns Data Model"
slug: "campaigns-data"
category: "campaigns"
order: 4
status: "published"
summary: "- id: UUID (PK) - name: CharField - description: TextField - kind: CharField (static/dynamic) - rules: JSONField - size: PositiveIntegerField (cached count) - materialized_at: DateTimeField - is_draft"
tags: ["campaigns"]
---

## Overview

- id: UUID (PK) - name: CharField - description: TextField - kind: CharField (static/dynamic) - rules: JSONField - size: PositiveIntegerField (cached count) - materialized_at: DateTimeField - is_draft

# campaigns - Data

## Owned Data Models

### Audience

- id: UUID (PK)
- name: CharField
- description: TextField
- kind: CharField (static/dynamic)
- rules: JSONField
- size: PositiveIntegerField (cached count)
- materialized_at: DateTimeField
- is_draft: BooleanField
- contacts: M2M → crm.Contact (through AudienceMembership)
- tenant: FK → Tenant

### AudienceMembership

- id: UUID (PK)
- audience: FK → Audience
- contact: FK → crm.Contact
- tenant: FK → Tenant

Constraints: unique (audience, contact)

### Campaign

- id: UUID (PK)
- name: CharField
- description: TextField
- channel: CharField (email, whatsapp, telegram, sms)
- kind: CharField (express, one_shot, drip, planned)
- status: CharField (draft, ready, scheduled, active, ended, archived)
- audience: FK → Audience (nullable)
- config: JSONField
- sent, opened, responded: PositiveIntegerField (counters)
- tenant: FK → Tenant

### CampaignData

- id: UUID (PK)
- campaign: FK → Campaign
- variables: JSONField
- status: CharField (pending, sent, delivered, failed, skipped)
- attempts: PositiveSmallIntegerField
- last_error: TextField
- scheduled_at, sent_at, delivered_at: DateTimeField
- result: JSONField
- job: UUIDField
- tenant: FK → Tenant

### CampaignDataStaging

- id: UUID (PK)
- tenant: FK → Tenant
- campaign_id: UUIDField (optional)
- raw_data: JSONField
- mapped_data: JSONField (optional)
- import_source: CharField
- original_filename: CharField
- row_count: PositiveIntegerField
- errors: JSONField

## External Data Read

- portal.Tenant
- crm.Contact

## External Data Written

None directly (references only).
