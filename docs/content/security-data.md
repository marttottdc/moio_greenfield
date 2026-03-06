---
title: "Security Data Model"
slug: "security-data"
category: "api-reference"
order: 4
status: "published"
summary: "- id: UUID (PK) - service_name: CharField - scopes: JSONField (list of permission scopes) - tenant_id: CharField (optional, binds token to specific tenant) - duration_hours: PositiveIntegerField (defa"
tags: ["security"]
---

## Overview

- id: UUID (PK) - service_name: CharField - scopes: JSONField (list of permission scopes) - tenant_id: CharField (optional, binds token to specific tenant) - duration_hours: PositiveIntegerField (defa

# security - Data

## Owned Data Models

### ServiceToken

- id: UUID (PK)
- service_name: CharField
- scopes: JSONField (list of permission scopes)
- tenant_id: CharField (optional, binds token to specific tenant)
- duration_hours: PositiveIntegerField (default: 24)
- token: TextField (generated JWT)
- expires_at: DateTimeField (computed on generation)
- created_at, updated_at: DateTimeField

## External Data Read

- settings.SERVICE_TOKEN_SECRET

## External Data Written

None.
