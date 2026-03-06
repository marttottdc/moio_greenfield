---
title: "Crm Data Model"
slug: "crm-data"
category: "crm"
order: 4
status: "published"
summary: "- user_id: CharField (PK, unique, UUID string) - fullname, email, phone, whatsapp_name: CharField - first_name, last_name, display_name, nickname, initials: CharField - dob: DateField - language, time"
tags: ["crm"]
---

## Overview

- user_id: CharField (PK, unique, UUID string) - fullname, email, phone, whatsapp_name: CharField - first_name, last_name, display_name, nickname, initials: CharField - dob: DateField - language, time

# crm - Data

## Owned Data Models

### Contact

- user_id: CharField (PK, unique, UUID string)
- fullname, email, phone, whatsapp_name: CharField
- first_name, last_name, display_name, nickname, initials: CharField
- dob: DateField
- language, timezone: CharField
- mobile, alt_phone, email_secondary: CharField
- preferred_channel: CharField
- email_verified_at, phone_verified_at: DateTimeField
- do_not_contact, bounced: BooleanField
- bounce_reason: CharField
- title, department, seniority, company, company_website: CharField
- addresses: JSONField (list of address dicts)
- primary_address fields (country, city, postal_code, lat/lon, geohash)
- status, stage: CharField
- owner, created_by: FK → User
- score: IntegerField
- utm fields (source, medium, campaign, term, content)
- consent fields (email, whatsapp)
- social URLs (website, linkedin, twitter, instagram, facebook, github, telegram)
- commerce fields (external_customer_id, currency, lifetime_value, total_orders, loyalty)
- brief fields (facts, text, version, updated_at)
- id fields (country, type, last4, hash, encrypted, verified_at)
- dedupe_hash, merged_into: FK → self
- is_deleted: BooleanField
- external_ids, preferences, traits, tags: JSONField
- embedding: VectorField (128 dimensions)
- ctype: FK → ContactType
- linked_user: OneToOne → MoioUser
- tenant: FK → Tenant

Constraints:
- `unique_phone_tenant` (phone, tenant) when phone not empty
- `unique_email_tenant` (email, tenant) when email not empty

### ContactType

- id: UUID (PK)
- name: CharField (choices)
- default_agent: FK → AgentConfiguration
- tenant: FK → Tenant

Constraint: unique (tenant, name)

### Company

- name, legal_name: CharField
- tenant: FK → Tenant

### Branch

- name, address, city, state, postal_code, type, category: CharField
- latitude, longitude: FloatField
- empresa: FK → Company
- contacto: FK → Contact
- geocoded: BooleanField
- website, phone, email: CharField
- visibility: CharField
- tenant: FK → Tenant

### Ticket

- id: UUID (PK)
- type: CharField (I, C, P)
- service, description: CharField/TextField
- creator, assigned, waiting_for: FK → Contact
- status: CharField
- origin_type: CharField
- origin_ref: CharField
- origin_session: FK → ChatbotSession
- tenant: FK → Tenant

### TicketComment

- id: UUID (PK)
- ticket: FK → Ticket
- comment: TextField
- creator: FK → Contact

### Pipeline

- id: UUID (PK)
- name, description: CharField/TextField
- is_default, is_active: BooleanField
- tenant: FK → Tenant

Constraint: unique (tenant, name)

### PipelineStage

- id: UUID (PK)
- pipeline: FK → Pipeline
- name, description: CharField/TextField
- order: PositiveIntegerField
- probability: PositiveIntegerField (0-100)
- is_won_stage, is_lost_stage: BooleanField
- color: CharField
- tenant: FK → Tenant

### Deal

- id: UUID (PK)
- title, description: CharField/TextField
- contact: FK → Contact
- pipeline: FK → Pipeline
- stage: FK → PipelineStage
- value: DecimalField
- currency: CharField
- probability: PositiveIntegerField
- priority, status: CharField
- expected_close_date, actual_close_date: DateField
- owner, created_by: FK → User
- won_reason, lost_reason, notes: TextField
- metadata, comments: JSONField
- tenant: FK → Tenant

### Product

- id: UUID (PK)
- name, description: CharField/TextField
- price, sale_price: FloatField
- brand, sku, category: CharField
- product_type: CharField (STD, VAR)
- attributes: JSONField
- tags: M2M → Tag
- embedding: VectorField (1536 dimensions)
- tenant: FK → Tenant

### ProductVariant

- id: UUID (PK)
- product: FK → Product
- sku, variant_name, description: CharField/TextField
- price, sale_price: FloatField
- tenant: FK → Tenant

### Stock

- id: UUID (PK)
- sku: CharField
- quantity: IntegerField
- tenant: FK → Tenant

### Tag

- name, slug: CharField
- description: TextField
- embedding: VectorField (1536 dimensions)
- context: CharField
- tenant: FK → Tenant

Constraints:
- unique (tenant_id, name, context)
- unique (tenant_id, slug, context)

### KnowledgeItem

- id: UUID (PK)
- title: CharField (unique)
- description: TextField
- url: URLField
- type, category: CharField
- embedding: VectorField (1536 dimensions)
- visibility: CharField
- slug: SlugField
- data: JSONField
- tenant: FK → Tenant

### ActivityType

- id: UUID (PK)
- tenant: FK → Tenant
- key: CharField (unique per tenant)
- label, name: CharField
- category: CharField (communication, meeting, visit, proposal, task, other)
- schema: JSONField (JSON Schema for content validation)
- default_duration_minutes, sla_days: IntegerField
- default_visibility, default_status: CharField
- icon, color, title_template: CharField
- requires_contact, requires_deal: BooleanField
- order: PositiveIntegerField

### ActivityRecord

- id: UUID (PK)
- tenant: FK → Tenant
- title: CharField
- content: JSONField
- user, owner, created_by: FK → User
- source: CharField (manual, system, suggestion)
- visibility: CharField
- type: FK → ActivityType
- kind: CharField (note, task, idea, event, other)
- status: CharField (planned, completed, cancelled, expired)
- scheduled_at, occurred_at, completed_at: DateTimeField
- duration_minutes: IntegerField
- contact: FK → Contact
- client: FK → Client
- deal: FK → Deal
- ticket: FK → Ticket
- tags: JSONField
- reason: CharField
- needs_confirmation: BooleanField

### ActivitySuggestion

- id: UUID (PK)
- tenant: FK → Tenant
- type_key: CharField
- reason: CharField
- confidence: FloatField
- suggested_at, expires_at: DateTimeField
- proposed_fields: JSONField
- target_contact_id, target_client_id, target_deal_id: CharField/UUIDField
- assigned_to: FK → User
- status: CharField (pending, accepted, dismissed)
- activity_record: OneToOne → ActivityRecord
- created_by_source: CharField

### WebhookConfig

- id: UUID (PK)
- name: CharField (unique)
- description: TextField
- expected_schema: TextField
- expected_content_type, expected_origin: CharField
- store_payloads: BooleanField
- auth_type: CharField
- auth_config: JSONField
- handler_path: CharField
- url: URLField
- locked: BooleanField
- linked_flows: M2M → Flow
- tenant: FK → Tenant

### WebhookPayload

- id: UUID (PK)
- config: FK → WebhookConfig
- payload: JSONField
- status: CharField
- tenant: FK → Tenant

### Customer, Address, EcommerceOrder, EcommerceOrderLine, Shipment

(Legacy/alternative customer models with order tracking)

### Face, FaceDetection

- id: UUID (PK)
- image: ImageField
- embedding: VectorField (128 dimensions)
- contact: FK → Contact (Face)
- face: FK → Face (FaceDetection)
- tenant: FK → Tenant

## External Data Read

- portal.Tenant
- portal.MoioUser
- chatbot.AgentConfiguration
- chatbot.ChatbotSession
- flows.Flow

## External Data Written

None directly.
