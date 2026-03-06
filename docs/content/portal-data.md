---
title: "Portal Data Model"
slug: "portal-data"
category: "integrations"
order: 4
status: "published"
summary: "- id: AutoField (PK) - nombre: CharField - enabled: BooleanField - domain: CharField - subdomain: CharField (unique) - plan: CharField (free, pro, business) - tenant_code: UUIDField (unique) - created"
tags: ["portal"]
---

## Overview

- id: AutoField (PK) - nombre: CharField - enabled: BooleanField - domain: CharField - subdomain: CharField (unique) - plan: CharField (free, pro, business) - tenant_code: UUIDField (unique) - created

# portal - Data

## Owned Data Models

### Tenant

- id: AutoField (PK)
- nombre: CharField
- enabled: BooleanField
- domain: CharField
- subdomain: CharField (unique)
- plan: CharField (free, pro, business)
- tenant_code: UUIDField (unique)
- created: DateTimeField

### MoioUser

- id: AutoField (PK)
- email: EmailField (unique)
- username: CharField (unique)
- first_name, last_name: CharField
- phone: CharField
- is_active, is_staff, is_superuser: BooleanField
- last_login, created: DateTimeField
- avatar: ImageField
- preferences: JSONField
- tenant: FK → Tenant
- groups: M2M → auth.Group
- user_permissions: M2M → auth.Permission

### AuthSession

- user: OneToOne → MoioUser
- refresh_token, session_token: CharField (unique)
- created_at, updated_at: DateTimeField
- revoked_at: DateTimeField

### PortalConfiguration

- site_name, company: CharField
- my_url: URLField
- logo, favicon: ImageField
- whatsapp_webhook_token: CharField
- whatsapp_webhook_redirect: URLField
- fb_* fields: Facebook/Meta configuration
- google_oauth_*, microsoft_oauth_*: OAuth configuration

### TenantConfiguration

- tenant: FK → Tenant
- google_*, openai_*, whatsapp_*, hiringroom_*, psigma_*, zetaSoftware_*, woocommerce_*, wordpress_*, dac_*, mercadopago_*, smtp_*: Integration fields
- assistants_*, chatbot_*, agent_*: AI configuration
- organization_*: Currency, timezone, date/time format
- default_notification_list: TextField

### IntegrationConfig

- id: UUID (PK)
- slug: CharField (integration type)
- instance_id: CharField (default: "default")
- name: CharField
- enabled: BooleanField
- config: JSONField
- metadata: JSONField
- tenant: FK → Tenant

Constraint: unique (tenant, slug, instance_id)

### Document

- file: FileField
- tenant: FK → Tenant

### Instruction

- key: CharField
- prompt: TextField
- tenant: FK → Tenant

### Notification

- id: UUID (PK)
- type, message, source, severity, to: CharField
- read: BooleanField
- tenant: FK → Tenant

### AppConfig

- id: UUID (PK)
- name, description: CharField
- icon: CharField
- enabled: BooleanField
- tenants: M2M → Tenant
- default_screen: CharField

### AppMenu

- id: UUID (PK)
- app, url, type: CharField
- enabled: BooleanField
- title, description, perm_group: CharField
- target_area: CharField
- icon, context: CharField

### ComponentTemplate

- name: CharField
- slug: SlugField
- description: TextField
- template_path: CharField
- context_schema: JSONField
- tenant: FK → Tenant

Constraint: unique (tenant, slug)

### ContentBlock

- component: FK → ComponentTemplate
- group: SlugField
- title: CharField
- order: PositiveIntegerField
- context: JSONField
- visibility: CharField
- is_active: BooleanField
- tenant: FK → Tenant

Constraint: unique (tenant, group, order)

## External Data Read

None (foundational app).

## External Data Written

- IntegrationConfig synced from TenantConfiguration on save
