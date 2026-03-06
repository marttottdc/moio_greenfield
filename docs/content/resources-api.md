---
title: "Resources API"
slug: "resources-api"
category: "api-reference"
order: 2
status: "published"
summary: "Base path: `/api/v1/resources/`"
tags: ["resources"]
---

## Overview

Base path: `/api/v1/resources/`

# resources - Interfaces

## Public Endpoints

Base path: `/api/v1/resources/`

### ContactSearchView

- `GET /api/v1/resources/contacts/search/?q=<query>` - Search contacts by fullname, email, or phone

### WhatsappTemplateViewSet

- `GET /api/v1/resources/whatsapp-templates/` - List WhatsApp templates for tenant
- `GET /api/v1/resources/whatsapp-templates/<id>/` - Get template details
- `POST /api/v1/resources/whatsapp-templates/<id>/send-test/` - Send test message

## Events Emitted

None.

## Events Consumed

None.

## Input/Output Schemas

### Contact Search Response

```json
{
  "results": [
    {
      "user_id": "uuid",
      "fullname": "string",
      "email": "string",
      "phone": "string"
    }
  ]
}
```

### WhatsApp Templates Response

```json
{
  "templates": [...]
}
```
