---
title: "Fluidcms Data Model"
slug: "fluidcms-data"
category: "integrations"
order: 4
status: "published"
summary: "- id: UUID (PK) - contact: FK → crm.Contact - referral_source, utm_source, utm_medium, utm_campaign: CharField - metadata: JSONField - total_messages: PositiveIntegerField - last_engaged_at: DateTimeF"
tags: ["fluidcms"]
---

## Overview

- id: UUID (PK) - contact: FK → crm.Contact - referral_source, utm_source, utm_medium, utm_campaign: CharField - metadata: JSONField - total_messages: PositiveIntegerField - last_engaged_at: DateTimeF

# fluidcms - Data

## Owned Data Models

### VisitorSession

- id: UUID (PK)
- contact: FK → crm.Contact
- referral_source, utm_source, utm_medium, utm_campaign: CharField
- metadata: JSONField
- total_messages: PositiveIntegerField
- last_engaged_at: DateTimeField

### Topic

- slug: SlugField (PK)
- title: CharField
- short_description: TextField
- icon, color: CharField
- image: URLField
- marketing_copy: TextField
- benefits, use_cases, pricing_tiers, features, cta: JSONField
- markdown: TextField
- metadata: JSONField

### TopicVisit

- session: FK → VisitorSession
- topic: FK → Topic
- visited_at: DateTimeField

### Conversation

- session: FK → VisitorSession
- topic: FK → Topic
- conversation_date: DateField
- started_at, last_message_at: DateTimeField
- metadata: JSONField

Constraint: unique (session, topic, conversation_date)

### ConversationMessage

- conversation: FK → Conversation
- session: FK → VisitorSession
- topic: FK → Topic
- role: CharField (user, assistant)
- content: TextField
- suggestions: JSONField
- metadata: JSONField
- conversation_sequence, session_sequence: PositiveIntegerField

### ConversationTurn (alternate)

- session: FK → VisitorSession
- topic: FK → Topic
- user_message, assistant_message: TextField
- suggestions: JSONField

### Like

- session: FK → VisitorSession
- topic: FK → Topic
- message_index: PositiveIntegerField
- message: FK → ConversationMessage

### EmailLog

- session: FK → VisitorSession
- recipient: EmailField
- subject: CharField
- body: TextField
- summary_included: BooleanField

### WhatsAppLog

- session: FK → VisitorSession
- recipient: CharField
- status: CharField
- template_name: CharField
- deep_link: URLField
- payload: JSONField

### MeetingBooking

- session: FK → VisitorSession
- attendee_name: CharField
- attendee_email: EmailField
- provider: CharField (calendly, google, custom)
- scheduled_for: DateTimeField
- confirmation_message: CharField
- calendar_url: URLField
- metadata: JSONField

### FluidPage

- id: UUID (PK)
- slug: SlugField
- name: CharField
- description: TextField
- layout: CharField
- status: CharField
- is_active, is_home: BooleanField
- default_locale: CharField
- metadata: JSONField
- tenant: FK → Tenant

Constraint: unique (tenant, slug)

### FluidBlock

- id: UUID (PK)
- page: FK → FluidPage
- key: CharField
- type: CharField (block types)
- layout, config: JSONField
- locale, fallback_locale: CharField
- order: PositiveIntegerField
- is_active: BooleanField
- metadata: JSONField
- tenant: FK → Tenant

### FluidMedia

- id: UUID (PK)
- file: FileField
- filename: CharField
- type: CharField (image, video, document, other)
- mime_type: CharField
- size: PositiveIntegerField
- metadata: JSONField
- tenant: FK → Tenant

### ArticleCategory

- id: UUID (PK)
- name: CharField
- slug: SlugField
- description: TextField
- parent: FK → self
- order: PositiveIntegerField
- is_active: BooleanField
- tenant: FK → Tenant

### ArticleTag

- id: UUID (PK)
- name: CharField
- slug: SlugField
- color: CharField
- tenant: FK → Tenant

### Article

- id: UUID (PK)
- author: FK → MoioUser
- title: CharField
- slug: SlugField
- excerpt, content: TextField
- category: FK → ArticleCategory
- tags: M2M → ArticleTag
- featured_image: FK → FluidMedia
- status: CharField
- published_at: DateTimeField
- metadata: JSONField
- view_count: PositiveIntegerField
- reading_time_minutes: PositiveIntegerField
- tenant: FK → Tenant

### BlockBundle

- id: UUID (PK)
- name: CharField
- slug: SlugField (unique)
- description: TextField
- author: CharField
- is_global: BooleanField
- tenant: FK → Tenant (null for global)
- metadata: JSONField

### BlockBundleVersion

- id: UUID (PK)
- bundle: FK → BlockBundle
- version: CharField (semantic version)
- changelog: TextField
- status: CharField (draft, submitted, published, deprecated)
- manifest: JSONField
- compatibility_range: JSONField
- published_at: DateTimeField
- published_by: FK → MoioUser

### BlockDefinition

- id: UUID (PK)
- bundle_version: FK → BlockBundleVersion
- block_type_id: CharField
- name: CharField
- description: TextField
- icon, category: CharField
- variants, feature_toggles: JSONField
- style_axes, content_slots, defaults: JSONField
- preview_template: TextField
- metadata: JSONField

### BundleInstall

- id: UUID (PK)
- bundle_version: FK → BlockBundleVersion
- status: CharField (active, inactive)
- installed_at: DateTimeField
- installed_by: FK → MoioUser
- activated_at: DateTimeField
- metadata: JSONField
- tenant: FK → Tenant

### PageVersion

- id: UUID (PK)
- page: FK → FluidPage
- version_number: PositiveIntegerField
- composition: JSONField
- content_pins: JSONField
- published_by: FK → MoioUser
- published_at: DateTimeField
- metadata: JSONField
- tenant: FK → Tenant

## External Data Read

- crm.Contact
- portal.Tenant
- portal.MoioUser

## External Data Written

None directly.
