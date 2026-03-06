---
title: "Resources Lifecycle"
slug: "resources-lifecycle"
category: "api-reference"
order: 3
status: "published"
summary: "No explicit startup behavior defined."
tags: ["resources"]
---

## Overview

No explicit startup behavior defined.

# resources - Lifecycle

## Startup Behavior

No explicit startup behavior defined.

## Runtime Behavior

### Contact Search

- Filters crm.Contact by tenant
- Matches fullname, email, or phone via icontains
- Returns max 20 results

### WhatsApp Template Operations

- Templates fetched from WhatsApp Business API via WhatsappBusinessClient
- Requires whatsapp_integration_enabled in TenantConfiguration
- Test messages sent via WhatsApp Business API

## Shutdown Behavior

No explicit shutdown behavior defined.
