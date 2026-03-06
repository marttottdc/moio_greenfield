# Moio CRM - Backend API Documentation

**Version:** 1.0  
**Base URL:** `https://api.moiodigital.com/v1`  
**Protocol:** REST API  
**Authentication:** JWT Bearer Token  
**Data Format:** JSON

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Settings API](#settings-api)
4. [Contacts API](#contacts-api)
5. [Communications API](#communications-api)
6. [Campaigns API](#campaigns-api)
7. [Audiences API](#audiences-api)
8. [Tickets API](#tickets-api)
9. [Flows API](#flows-api)
10. [Dashboard & Analytics](#dashboard--analytics)
11. [Data Models](#data-models)
12. [AI Agent Engine Integration](#ai-agent-engine-integration)
13. [Technical Specifications](#technical-specifications)

---

## Overview

This document provides complete API specifications for the Moio CRM frontend integration with the Moio Platform Django backend. The Moio Platform is an AI-enhanced CRM and workflow automation engine built by Moio Digital Services.

### Key Features
- RESTful API architecture
- JWT-based authentication
- Real-time updates via WebSockets (optional)
- AI agent integration for automation
- Multi-channel communication (WhatsApp, Email, etc.)
- Comprehensive workflow automation

---

## Authentication

### POST `/auth/login`
Authenticate user and receive JWT tokens.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "username": "string",
    "email": "string",
    "full_name": "string",
    "role": "admin|user|manager"
  }
}
```

**Error Response (401 Unauthorized):**
```json
{
  "error": "invalid_credentials",
  "message": "Invalid username or password"
}
```

---

### POST `/auth/refresh`
Refresh access token using refresh token.

**Request Body:**
```json
{
  "refresh_token": "string"
}
```

**Response (200 OK):**
```json
{
  "access_token": "string",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

---

### POST `/auth/logout`
Invalidate current session and tokens.

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response (200 OK):**
```json
{
  "message": "Successfully logged out"
}
```

---

### GET `/auth/me`
Get current authenticated user information.

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "username": "string",
  "email": "string",
  "full_name": "string",
  "role": "admin|user|manager",
  "avatar_url": "string|null",
  "organization": {
    "id": "uuid",
    "name": "string"
  },
  "preferences": {
    "theme": "light|dark",
    "language": "es|en",
    "timezone": "string"
  }
}
```

---

## Settings API

### GET `/settings/integrations`
List all available integrations and their connection status.

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response (200 OK):**
```json
{
  "integrations": [
    {
      "id": "whatsapp",
      "name": "WhatsApp Business",
      "description": "Customer messaging and support",
      "connected": true,
      "config": {
        "phone_number": "+598XXXXXXXXX",
        "business_name": "string"
      },
      "last_sync": "2025-11-12T10:30:00Z"
    },
    {
      "id": "openai",
      "name": "OpenAI",
      "description": "AI-powered assistance and automation",
      "connected": false,
      "config": null,
      "last_sync": null
    },
    {
      "id": "gmail",
      "name": "Gmail",
      "description": "Email communication and automation",
      "connected": false,
      "config": null,
      "last_sync": null
    }
  ]
}
```

---

### POST `/settings/integrations/{integration_id}/connect`
Connect or configure an integration.

**Path Parameters:**
- `integration_id`: Integration identifier (e.g., "whatsapp", "openai", "gmail")

**Request Body (varies by integration):**
```json
{
  "api_key": "string",
  "phone_number": "string",
  "additional_config": {}
}
```

**Response (200 OK):**
```json
{
  "id": "whatsapp",
  "name": "WhatsApp Business",
  "connected": true,
  "message": "Integration connected successfully",
  "config": {
    "phone_number": "+598XXXXXXXXX"
  }
}
```

---

### DELETE `/settings/integrations/{integration_id}`
Disconnect an integration.

**Response (200 OK):**
```json
{
  "message": "Integration disconnected successfully"
}
```

---

### GET `/settings/preferences`
Get user preferences and system settings.

**Response (200 OK):**
```json
{
  "user_preferences": {
    "theme": "light|dark",
    "language": "es|en",
    "timezone": "America/Montevideo",
    "notifications": {
      "email": true,
      "push": true,
      "desktop": false
    },
    "dashboard_layout": "compact|expanded"
  },
  "system_settings": {
    "organization_name": "string",
    "currency": "USD|UYU",
    "date_format": "DD/MM/YYYY",
    "time_format": "24h|12h"
  }
}
```

---

### PATCH `/settings/preferences`
Update user preferences.

**Request Body:**
```json
{
  "theme": "light",
  "language": "es",
  "notifications": {
    "email": true,
    "push": false
  }
}
```

**Response (200 OK):**
```json
{
  "message": "Preferences updated successfully",
  "preferences": {
    "theme": "light",
    "language": "es",
    "timezone": "America/Montevideo",
    "notifications": {
      "email": true,
      "push": false,
      "desktop": false
    }
  }
}
```

---

## Contacts API

### GET `/contacts`
List all contacts with filtering and pagination.

**Query Parameters:**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 50, max: 100): Items per page
- `search` (string): Search by name, email, or phone
- `type` (string): Filter by contact type (Lead|Customer|Partner|Vendor)
- `sort_by` (string, default: "created_at"): Sort field
- `order` (string, default: "desc"): Sort order (asc|desc)

**Example Request:**
```
GET /contacts?page=1&limit=50&type=Lead&search=zapata&sort_by=name&order=asc
```

**Response (200 OK):**
```json
{
  "contacts": [
    {
      "id": "uuid",
      "name": "LUIS ZAPATA",
      "email": "luis.zapata@example.com",
      "phone": "+59892637130",
      "company": "Tech Solutions SA",
      "type": "Lead",
      "created_at": "2025-11-01T10:30:00Z",
      "updated_at": "2025-11-10T15:45:00Z",
      "tags": ["interested", "tech"],
      "custom_fields": {
        "source": "Website",
        "industry": "Technology"
      }
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 50,
    "total_items": 2476,
    "items_per_page": 50
  }
}
```

---

### POST `/contacts`
Create a new contact.

**Request Body:**
```json
{
  "name": "MATÍAS CASTRO",
  "email": "matias.castro@example.com",
  "phone": "+59894790642",
  "company": "Castro Enterprises",
  "type": "Lead",
  "tags": ["new", "priority"],
  "custom_fields": {
    "source": "Referral",
    "industry": "Retail"
  }
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "name": "MATÍAS CASTRO",
  "email": "matias.castro@example.com",
  "phone": "+59894790642",
  "company": "Castro Enterprises",
  "type": "Lead",
  "created_at": "2025-11-12T10:30:00Z",
  "updated_at": "2025-11-12T10:30:00Z",
  "tags": ["new", "priority"],
  "custom_fields": {
    "source": "Referral",
    "industry": "Retail"
  }
}
```

---

### GET `/contacts/{id}`
Get a specific contact by ID.

**Path Parameters:**
- `id`: Contact UUID

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "LUIS ZAPATA",
  "email": "luis.zapata@example.com",
  "phone": "+59892637130",
  "company": "Tech Solutions SA",
  "type": "Customer",
  "created_at": "2025-11-01T10:30:00Z",
  "updated_at": "2025-11-10T15:45:00Z",
  "tags": ["vip", "tech"],
  "custom_fields": {},
  "activity_summary": {
    "total_deals": 3,
    "total_tickets": 5,
    "total_messages": 47,
    "last_contact": "2025-11-11T18:36:00Z"
  }
}
```

---

### PATCH `/contacts/{id}`
Update an existing contact.

**Request Body (partial updates allowed):**
```json
{
  "type": "Customer",
  "tags": ["vip", "priority"],
  "company": "Updated Company Name"
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "LUIS ZAPATA",
  "email": "luis.zapata@example.com",
  "phone": "+59892637130",
  "company": "Updated Company Name",
  "type": "Customer",
  "updated_at": "2025-11-12T11:00:00Z",
  "tags": ["vip", "priority"]
}
```

---

### DELETE `/contacts/{id}`
Delete a contact.

**Response (200 OK):**
```json
{
  "message": "Contact deleted successfully"
}
```

---

### POST `/contacts/import`
Bulk import contacts from CSV or JSON.

**Request Body (multipart/form-data):**
```
file: contacts.csv
```

**Or JSON:**
```json
{
  "contacts": [
    {
      "name": "Contact 1",
      "email": "contact1@example.com",
      "phone": "+598XXXXXXXXX",
      "type": "Lead"
    },
    {
      "name": "Contact 2",
      "email": "contact2@example.com",
      "phone": "+598XXXXXXXXX",
      "type": "Customer"
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "message": "Import completed",
  "imported": 47,
  "failed": 3,
  "errors": [
    {
      "row": 12,
      "error": "Invalid email format"
    }
  ]
}
```

---

### GET `/contacts/export`
Export contacts as CSV or JSON.

**Query Parameters:**
- `format` (string): Export format (csv|json)
- `type` (string, optional): Filter by type
- `tags` (string, optional): Filter by tags (comma-separated)

**Response (200 OK):**
Returns file download with appropriate content-type.

---

### GET `/contacts/stats`
Get contact statistics and metrics.

**Response (200 OK):**
```json
{
  "total_contacts": 2476,
  "by_type": {
    "Lead": 1523,
    "Customer": 845,
    "Partner": 78,
    "Vendor": 30
  },
  "new_this_month": 1087,
  "active_contacts": 90,
  "growth_rate": 12.5
}
```

---

## Communications API

### GET `/communications/conversations`
List all conversation threads.

**Query Parameters:**
- `page` (integer): Page number
- `limit` (integer): Items per page
- `channel` (string): Filter by channel (WhatsApp|Email|SMS|Instagram|Telegram)
- `unread_only` (boolean): Show only unread conversations
- `search` (string): Search by contact name or phone

**Response (200 OK):**
```json
{
  "conversations": [
    {
      "id": "uuid",
      "contact": {
        "id": "uuid",
        "name": "LUIS ZAPATA",
        "phone": "+59892637130",
        "avatar_url": null
      },
      "channel": "WhatsApp",
      "last_message": {
        "id": "uuid",
        "content": "Confirmado: Luis Zapata ha confirmado su asistencia para la...",
        "sender": "contact",
        "timestamp": "2025-11-12T06:36:00Z",
        "status": "delivered"
      },
      "unread_count": 1,
      "updated_at": "2025-11-12T06:36:00Z",
      "tags": ["confirmation", "interview"]
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 3,
    "total_items": 70
  }
}
```

---

### GET `/communications/conversations/{id}`
Get full conversation thread with messages.

**Path Parameters:**
- `id`: Conversation UUID

**Query Parameters:**
- `limit` (integer, default: 50): Number of messages to retrieve
- `before` (string, optional): ISO timestamp to get messages before this time

**Response (200 OK):**
```json
{
  "id": "uuid",
  "contact": {
    "id": "uuid",
    "name": "LUIS ZAPATA",
    "phone": "+59892637130",
    "email": "luis.zapata@example.com"
  },
  "channel": "WhatsApp",
  "created_at": "2025-11-10T14:20:00Z",
  "updated_at": "2025-11-12T06:36:00Z",
  "messages": [
    {
      "id": "uuid",
      "content": "Hola Luis, te confirmamos tu entrevista para el día 12/11/2025 a las 11:00",
      "sender": "agent",
      "sender_name": "Moio CRM",
      "timestamp": "2025-11-11T10:00:00Z",
      "status": "read",
      "type": "text",
      "attachments": []
    },
    {
      "id": "uuid",
      "content": "Perfecto, allí estaré. Muchas gracias!",
      "sender": "contact",
      "sender_name": "LUIS ZAPATA",
      "timestamp": "2025-11-11T10:05:00Z",
      "status": "delivered",
      "type": "text",
      "attachments": []
    },
    {
      "id": "uuid",
      "content": "Confirmado: Luis Zapata ha confirmado su asistencia para la entrevista del 12/11/2025 a las 11:00",
      "sender": "system",
      "sender_name": "AI Agent",
      "timestamp": "2025-11-11T10:05:30Z",
      "status": "delivered",
      "type": "system_note",
      "attachments": []
    }
  ],
  "metadata": {
    "total_messages": 24,
    "ai_summary": "Luis Zapata confirmó asistencia para entrevista. Mostró entusiasmo y gratitud."
  }
}
```

---

### POST `/communications/conversations/{id}/messages`
Send a message in a conversation.

**Path Parameters:**
- `id`: Conversation UUID

**Request Body:**
```json
{
  "content": "Hola, te recordamos tu cita de mañana a las 10:00",
  "type": "text",
  "attachments": [
    {
      "type": "image",
      "url": "https://cdn.moio.com/files/image.jpg",
      "filename": "confirmation.jpg"
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "conversation_id": "uuid",
  "content": "Hola, te recordamos tu cita de mañana a las 10:00",
  "sender": "agent",
  "timestamp": "2025-11-12T10:30:00Z",
  "status": "sent",
  "type": "text",
  "attachments": [
    {
      "type": "image",
      "url": "https://cdn.moio.com/files/image.jpg",
      "filename": "confirmation.jpg"
    }
  ]
}
```

---

### POST `/communications/conversations`
Create a new conversation/send first message.

**Request Body:**
```json
{
  "contact_id": "uuid",
  "channel": "WhatsApp",
  "message": {
    "content": "Hola! Te contactamos desde Moio Digital",
    "type": "text"
  }
}
```

**Response (201 Created):**
```json
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "status": "sent"
}
```

---

### PATCH `/communications/conversations/{id}/mark-read`
Mark all messages in conversation as read.

**Response (200 OK):**
```json
{
  "message": "Conversation marked as read",
  "unread_count": 0
}
```

---

### GET `/communications/stats`
Get communication statistics.

**Response (200 OK):**
```json
{
  "active_chats": 70,
  "unread_messages": 8,
  "avg_response_time": "5m",
  "active_users": 124,
  "by_channel": {
    "WhatsApp": 65,
    "Email": 3,
    "Instagram": 2
  },
  "messages_today": 247,
  "messages_this_week": 1532
}
```

---

## Campaigns API

### Base Path & Authentication
- **Router:** `/api/v1/campaigns/` (legacy references to `/campaigns/api/` map one-to-one to the new versioned namespace).
- **Authentication:** All endpoints enforce `IsAuthenticated`.
- **Transport:** JSON over HTTPS. Adjust the base path depending on how the router is mounted in the main Django project.
- **Source of truth:** the autogenerated OpenAPI schema is now published at https://moio.ngrok.dev/api/schema/ and should be used when wiring new consumers.

### Core Domain Objects & Shared Enums
- **Campaigns** contain metadata (name, description), delivery channel, lifecycle kind/status, audience selection, aggregate delivery metrics, and a `config` JSON blob that stores the builder state (message template, data mappings, defaults, schedule, etc.). The list serializer already returns derived properties such as `audience_name`, `audience_size`, `open_rate`, and `ready_to_launch`. The detail serializer adds the raw `config` and a `configuration_state` object with booleans for each step of the builder (audience, template, mapping, schedule, etc.).
- **Audiences** represent reusable recipient sets (see [Audiences API](#audiences-api)). Campaign responses embed `audience_name`, `audience_size`, and `audience_kind` so UI badges can reflect readiness.
- **WhatsApp templates** are proxied from the WhatsApp Business integration and exposed under `/api/v1/resources/whatsapp-templates/` for listing, inspection, and test sends.

**Enumerations exposed by the API**
- Channels: `email`, `whatsapp`, `telegram`, `sms`.
- Campaign kinds: `express`, `one_shot`, `drip`, `planned`.
- Campaign statuses: `draft`, `ready`, `scheduled`, `active`, `ended`, `archived`.
- Audience kinds: `static`, `dynamic` (returned by the dashboard endpoint for quick filters).

### Campaign CRUD (`/campaigns/api/campaigns/`)

#### GET `/campaigns/api/campaigns/`
Paginates campaigns ordered by `created` descending. Supports `search`, `status`, and `channel` query params. Each item follows `CampaignSerializer` so the UI already receives:
- `audience_name` / `audience_size`
- `open_rate` (percentage)
- `ready_to_launch` boolean to drive badge/CTA logic

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "0f0a...",
      "name": "Spring Sale Broadcast",
      "description": "Express WhatsApp campaign",
      "channel": "whatsapp",
      "kind": "express",
      "status": "ready",
      "audience_name": "VIP buyers",
      "audience_size": 1280,
      "audience_kind": "dynamic",
      "ready_to_launch": true,
      "open_rate": 64.2,
      "created_at": "2024-02-01T12:00:00Z"
    }
  ]
}
```

#### POST `/campaigns/api/campaigns/`
Creates a draft campaign. The backend injects tenant defaults via `set_base_config`, so the UI only needs to send top-level fields such as `name`, `description`, `channel`, and `kind`.

```json
{
  "name": "Product Launch",
  "description": "Initial outreach",
  "channel": "whatsapp",
  "kind": "one_shot"
}
```

**Response:** `201 Created` with the full `CampaignDetailSerializer`, including `config`, `configuration_state`, and server defaults under `config.defaults`.

#### GET `/campaigns/api/campaigns/{id}/`
Returns the detail serializer with embedded `config` and `configuration_state`. Use the booleans in `configuration_state` to render completion states across builder steps (audience selection, message template, mapping, schedule, etc.).

#### PATCH `/campaigns/api/campaigns/{id}/`
Updates top-level fields (`name`, `description`, `kind`, `status`, etc.). Mutations to nested builder data happen via the dedicated configuration actions listed below.

#### DELETE `/campaigns/api/campaigns/{id}/`
Inherited from `ModelViewSet`. Removes the campaign entirely.

### Dashboard & Analytics

#### GET `/campaigns/api/campaigns/dashboard/`
Returns a consolidated payload for the dashboard landing page:
- Latest campaigns list
- Audience list (with `kind`, `size`, `is_draft`)
- Enumerated options for channels/status filters
- `dashboard_metrics` summarizing campaign counts, total sent/opened, and open rate

#### GET `/campaigns/api/campaigns/analytics/?tenant&start_date&end_date&status&origin&q`
Returns daily messaging volume, delivery breakdowns (status buckets), top users, and WhatsApp conversation stats. Filters are optional; staff users may scope to a tenant. Dates are inclusive and expect `YYYY-MM-DD`.

### Configuration Actions (`/campaigns/api/campaigns/{id}/<action>/`)

Each action returns the refreshed detail serializer (or action-specific payload) so the UI can update immediately.

| Action | Method & Body | Behavior |
| --- | --- | --- |
| `duplicate/` | `POST` – empty body | Clones the campaign (excluding staged data) and returns the new detail payload. |
| `set-audience/` | `POST {"audience_id": "<uuid>"}` | Validates tenant ownership, sets `campaign.audience`, and returns the updated detail. Disable launch until the selected audience is finalized and `size > 0`. |
| `set-whatsapp-template/` | `POST {"template_id": "<id>"}` | Persists template metadata under `config.message`. Errors with `400` if the WhatsApp integration is disabled. Response echoes `template_id` plus computed variable requirements. |
| `set-defaults/` | `POST` with any subset of `{auto_correct, use_first_name, save_contacts, notify_agent, contact_type, country_code}` | Merges into `config.defaults` to persist builder toggles. |
| `map-template/` | `POST {"mapping": [{"template_var": "1", "target_field": "contact.custom_field", "type": "text"}, ...], "contact_name_field": "contacts.full_name"}` | Saves field mappings to `config.message.map`. Automatically appends a `contact_name` entry if `contact_name_field` is provided. Response returns the saved mapping. |
| `schedule/` | `POST {"date": "2024-05-01T15:00:00Z"}` (or `null`) | Persists `config.schedule.date` and sets the campaign status to `scheduled`. Use immediately after the scheduling step. |
| `validate/` | `POST` – empty body | Triggers async validation. Response contains a Celery `job_id`; poll `/campaigns/api/campaigns/jobs/{job_id}/` until `ready: true` to surface validation errors. |
| `launch/` | `POST` – empty body | Starts delivery. Response returns an array of Celery `job_ids` representing the execution tasks. Surface them in the UI and optionally link to job-status polling. |

#### GET `/campaigns/api/campaigns/{id}/logs/`
Returns delivery logs combining CRM data and WhatsApp message timestamps:

```json
{
  "logs": [
    {
      "msg_id": "wamid.HBgL...",
      "contact_number": "+5989XXXXXXX",
      "timestamps": {
        "sent": "2024-03-20T10:00:00Z",
        "delivered": "2024-03-20T10:00:03Z",
        "read": "2024-03-20T10:01:10Z",
        "failed": null
      },
      "campaign_data": {
        "contact": {
          "full_name": "Jane Doe",
          "email": "jane@example.com"
        },
        "variables": {
          "order_id": "12345"
        }
      }
    }
  ]
}
```

#### GET `/campaigns/api/campaigns/jobs/{job_id}/`
Standard Celery inspector response:

```json
{
  "id": "65f0c...",
  "status": "started",
  "ready": false,
  "success": null,
  "result": null
}
```

UI workflows should poll this endpoint for `validate` and `launch` jobs until `ready` becomes `true`. Use `result` content for error presentation.

### WhatsApp Template Endpoints (`/campaigns/api/whatsapp-templates/`)

- **GET `/whatsapp-templates/`** – Lists templates available through the WhatsApp Business integration, returning `id`, `name`, `category`, `language`, `status`, and raw `components`. If the integration is disabled the endpoint returns an empty list so the UI can show a helpful empty state.
- **GET `/whatsapp-templates/{id}/`** – Returns `{ "template": <raw template>, "requirements": <placeholder requirements> }`. Feed this data into the variable-mapping UI.
- **POST `/whatsapp-templates/{id}/send-test/`** – Body `{ "phone": "+5989...", "variables": { ... } }`. Sends a test message and responds with `{ "sent": true }`. Missing-integration errors surface as `400` so the UI can prompt the user to configure WhatsApp first.

### Contact Search
- **GET `/campaigns/api/contacts/search/?q=<term>`** – Performs tenant-scoped fuzzy search across contacts’ names, emails, and phone numbers. Requires at least two characters; shorter queries return `{ "results": [] }`. Responses contain up to 20 matches with `{ id, fullname, email, phone }`, which are ideal for autocomplete pickers when selecting static contacts or mapping CRM fields.

----
## Audiences API

Audience endpoints live under `/campaigns/api/audiences/` and reuse DRF `ModelViewSet` authentication.

### CRUD
- **GET `/campaigns/api/audiences/`** – Paginates audiences ordered by `created` descending. Each item returns `name`, `kind` (`static` or `dynamic`), `size`, `is_draft`, timestamps, and convenience labels for quick filters.
- **POST `/campaigns/api/audiences/`** – Creates a new audience (defaults to `is_draft = true` until finalized).
- **GET `/campaigns/api/audiences/{id}/`** – Returns `AudienceDetailSerializer`, including the stored rules JSON for dynamic audiences.
- **PATCH `/campaigns/api/audiences/{id}/`** – Updates metadata or rules (dynamic). Use dedicated helpers below for large rule edits or static membership changes.
- **DELETE `/campaigns/api/audiences/{id}/`** – Deletes the audience.

### Dynamic Audiences
- **POST `/campaigns/api/audiences/{id}/dynamic/preview/`** – Body `{ "and_rules": [...], "or_rules": [...] }`. Evaluates the rules without persisting and returns `{ "count": <int> }` so you can power “live match preview” UX.
- **POST `/campaigns/api/audiences/{id}/dynamic/autosave/`** – Same payload. Persists `audience.rules`, keeps `is_draft = true`, recomputes membership via `compute_audience`, and responds with `{ "count": <matched contacts> }`. Ideal for autosave flows while editing rule builders.
- **POST `/campaigns/api/audiences/{id}/dynamic/finalize/`** – Commits rules, clears `is_draft`, recomputes membership, and stores `audience.size`. Response is the refreshed detail serializer, ready for use by campaigns.

### Static Audiences
- **POST `/campaigns/api/audiences/{id}/static/contacts/`** – Body `{ "contact_ids": ["uuid", ...], "action": "add" | "remove" }`. Requires `kind == static`, adjusts membership through helper services, and returns `{ "affected": <count>, "size": <new size> }` so the UI can update counts immediately.
- **POST `/campaigns/api/audiences/{id}/static/finalize/`** – Recounts membership, clears `is_draft`, and returns the detail serializer.
- **GET `/campaigns/api/audiences/{id}/contacts/`** – Returns the latest 50 members plus the overall count: `{ "results": [{"id": "uuid", "fullname": "...", "phone": "...", "email": "..."}, ...], "count": 123 }`. Use for preview panels or drilldowns.

### Draft vs. Finalized State
Both campaigns and audiences expose `is_draft`. Campaign launch and scheduling actions should be disabled until:
- The linked audience is finalized (`is_draft = false`).
- The audience `size` is greater than zero.
- `configuration_state` flags show all required steps as complete.

### Async Workflows & Error Handling
- `validate/` and `launch/` actions return Celery job IDs. Always poll `/campaigns/api/campaigns/jobs/{job_id}/` until `ready` becomes `true`.
- WhatsApp-related endpoints (`set-whatsapp-template`, template listing/send-test) return `400` when the integration is not configured. Surface the backend `detail` message to guide users.
- Contact search enforces a minimum query length. Mirror this client-side to avoid unnecessary round trips.

### Metrics Guidance
Dashboard metrics (counts, total sent/opened, open rate, etc.) are precomputed server-side. Prefer rendering the provided aggregates instead of recomputing on the client.

### Audience Counts
For large audiences rely on the canonical `size` field returned by API responses. Endpoints like `static/contacts` always return the refreshed size after mutations, so the UI never needs to count manually.

### Async Validation & Launch Jobs
Use job IDs returned from `validate/` and `launch/` to show background progress. Present failures from the `result` payload when `success` is `false`.

### Logs and Timeline Views
`/campaigns/api/campaigns/{id}/logs/` merges CRM personalization data with WhatsApp message log timestamps. Use `campaign_data` entries to show variable substitutions or contact info in run-level drilldowns.

----
## Tickets API

### GET `/tickets`
List all support tickets with filtering.

**Query Parameters:**
- `page` (integer): Page number
- `limit` (integer): Items per page
- `status` (string): Filter by status (Open|In Progress|Resolved|Closed)
- `priority` (string): Filter by priority (High|Medium|Low)
- `assigned_to` (string): Filter by assigned user ID
- `search` (string): Search by subject or customer

**Response (200 OK):**
```json
{
  "tickets": [
    {
      "id": "uuid",
      "ticket_number": "TICK-2024-001",
      "subject": "Verificar el estado de confirmación de Bela para las entrevistas programadas",
      "customer": {
        "id": "uuid",
        "name": "BELEN",
        "email": "belen@example.com",
        "phone": "+598XXXXXXXXX"
      },
      "status": "Open",
      "priority": "High",
      "assigned_to": {
        "id": "uuid",
        "name": "María García",
        "avatar_url": null
      },
      "category": "recruitment",
      "created_at": "2025-11-11T18:36:00Z",
      "updated_at": "2025-11-11T18:36:00Z",
      "due_date": "2025-11-12T18:00:00Z",
      "tags": ["urgent", "interview"]
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 32,
    "total_items": 245
  }
}
```

---

### POST `/tickets`
Create a new support ticket.

**Request Body:**
```json
{
  "subject": "Consulta sobre cambio de horario",
  "description": "El cliente solicita modificar su horario de trabajo",
  "customer_id": "uuid",
  "priority": "Medium",
  "category": "general_inquiry",
  "tags": ["schedule_change"]
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "ticket_number": "TICK-2024-246",
  "subject": "Consulta sobre cambio de horario",
  "status": "Open",
  "priority": "Medium",
  "created_at": "2025-11-12T10:30:00Z"
}
```

---

### GET `/tickets/{id}`
Get ticket details with full conversation history.

**Response (200 OK):**
```json
{
  "id": "uuid",
  "ticket_number": "TICK-2024-001",
  "subject": "Verificar el estado de confirmación de Bela",
  "description": "Se necesita verificar si Bela confirmó para las entrevistas del 12/11/2025",
  "customer": {
    "id": "uuid",
    "name": "BELEN",
    "email": "belen@example.com",
    "phone": "+598XXXXXXXXX"
  },
  "status": "In Progress",
  "priority": "High",
  "category": "recruitment",
  "assigned_to": {
    "id": "uuid",
    "name": "María García",
    "email": "maria@moiodigital.com"
  },
  "created_at": "2025-11-11T18:36:00Z",
  "updated_at": "2025-11-12T09:15:00Z",
  "due_date": "2025-11-12T18:00:00Z",
  "tags": ["urgent", "interview", "confirmation"],
  "activity": [
    {
      "id": "uuid",
      "type": "comment",
      "author": {
        "id": "uuid",
        "name": "María García"
      },
      "content": "Contacté a Bela por WhatsApp, esperando respuesta",
      "timestamp": "2025-11-12T09:15:00Z",
      "attachments": []
    },
    {
      "id": "uuid",
      "type": "status_change",
      "author": {
        "id": "uuid",
        "name": "Sistema"
      },
      "content": "Estado cambiado de 'Open' a 'In Progress'",
      "timestamp": "2025-11-12T09:14:00Z"
    }
  ],
  "related_items": {
    "contacts": ["uuid"],
    "conversations": ["uuid"],
    "deals": []
  }
}
```

---

### PATCH `/tickets/{id}`
Update ticket details.

**Request Body:**
```json
{
  "status": "Resolved",
  "priority": "Low",
  "assigned_to": "uuid",
  "tags": ["resolved", "confirmed"]
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "status": "Resolved",
  "updated_at": "2025-11-12T10:30:00Z",
  "message": "Ticket updated successfully"
}
```

---

### POST `/tickets/{id}/comments`
Add a comment/note to a ticket.

**Request Body:**
```json
{
  "content": "Bela confirmó su asistencia. Todo listo para la entrevista del 12/11.",
  "internal": false,
  "attachments": [
    {
      "type": "file",
      "url": "https://cdn.moio.com/files/confirmation.pdf",
      "filename": "confirmation.pdf"
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "ticket_id": "uuid",
  "content": "Bela confirmó su asistencia. Todo listo para la entrevista del 12/11.",
  "author": {
    "id": "uuid",
    "name": "María García"
  },
  "internal": false,
  "timestamp": "2025-11-12T10:30:00Z",
  "attachments": [
    {
      "type": "file",
      "url": "https://cdn.moio.com/files/confirmation.pdf",
      "filename": "confirmation.pdf"
    }
  ]
}
```

---

### DELETE `/tickets/{id}`
Delete a ticket.

**Response (200 OK):**
```json
{
  "message": "Ticket deleted successfully"
}
```

---

### GET `/tickets/stats`
Get ticket statistics and metrics.

**Response (200 OK):**
```json
{
  "total_tickets": 245,
  "open": 123,
  "in_progress": 86,
  "resolved": 32,
  "closed": 4,
  "by_priority": {
    "High": 45,
    "Medium": 128,
    "Low": 72
  },
  "avg_resolution_time": "4h 23m",
  "avg_first_response_time": "12m",
  "tickets_today": 15,
  "tickets_this_week": 67
}
```

---

## Flows API

### GET `/flows`
List all workflow automation flows.

**Query Parameters:**
- `page` (integer): Page number
- `limit` (integer): Items per page
- `status` (string): Filter by status (Active|Disabled|Testing|Draft)
- `search` (string): Search by flow name

**Response (200 OK):**
```json
{
  "flows": [
    {
      "id": "uuid",
      "name": "Lead Nurturing Automation",
      "description": "Automatically nurture leads through the sales funnel",
      "status": "Active",
      "trigger": {
        "type": "contact_created",
        "conditions": {
          "contact_type": "Lead"
        }
      },
      "actions_count": 5,
      "executions": {
        "total": 1247,
        "successful": 1198,
        "failed": 49,
        "last_execution": "2025-11-12T10:15:00Z"
      },
      "created_at": "2025-10-01T10:00:00Z",
      "updated_at": "2025-11-10T14:30:00Z",
      "created_by": {
        "id": "uuid",
        "name": "Admin User"
      }
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 1,
    "total_items": 1
  }
}
```

---

### POST `/flows`
Create a new workflow flow.

**Request Body:**
```json
{
  "name": "Welcome Message for New Contacts",
  "description": "Send automated welcome message when new contact is created",
  "status": "Testing",
  "trigger": {
    "type": "contact_created",
    "conditions": {
      "contact_type": "Lead"
    }
  },
  "actions": [
    {
      "type": "delay",
      "config": {
        "duration": 300,
        "unit": "seconds"
      }
    },
    {
      "type": "send_message",
      "config": {
        "channel": "WhatsApp",
        "template_id": "uuid",
        "variables": {
          "name": "{{contact.name}}"
        }
      }
    },
    {
      "type": "add_tag",
      "config": {
        "tags": ["welcomed"]
      }
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "name": "Welcome Message for New Contacts",
  "status": "Testing",
  "created_at": "2025-11-12T10:30:00Z",
  "message": "Flow created successfully"
}
```

---

### GET `/flows/{id}`
Get flow details with full configuration.

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "Lead Nurturing Automation",
  "description": "Automatically nurture leads through the sales funnel",
  "status": "Active",
  "trigger": {
    "type": "contact_created",
    "conditions": {
      "contact_type": "Lead",
      "source": "Website"
    }
  },
  "actions": [
    {
      "id": "action-1",
      "type": "send_message",
      "config": {
        "channel": "WhatsApp",
        "template_id": "uuid",
        "message": "Bienvenido {{contact.name}}!"
      },
      "position": 1
    },
    {
      "id": "action-2",
      "type": "delay",
      "config": {
        "duration": 86400,
        "unit": "seconds"
      },
      "position": 2
    },
    {
      "id": "action-3",
      "type": "conditional",
      "config": {
        "condition": "contact.tags contains 'interested'",
        "if_true": ["action-4"],
        "if_false": ["action-5"]
      },
      "position": 3
    },
    {
      "id": "action-4",
      "type": "create_deal",
      "config": {
        "title": "Oportunidad - {{contact.name}}",
        "stage": "qualified"
      },
      "position": 4
    }
  ],
  "metrics": {
    "total_executions": 1247,
    "successful": 1198,
    "failed": 49,
    "avg_execution_time": "2.3s",
    "last_execution": "2025-11-12T10:15:00Z"
  },
  "created_at": "2025-10-01T10:00:00Z",
  "updated_at": "2025-11-10T14:30:00Z"
}
```

---

### PATCH `/flows/{id}`
Update flow configuration.

**Request Body:**
```json
{
  "status": "Active",
  "description": "Updated description",
  "actions": [
    {
      "id": "action-1",
      "type": "send_message",
      "config": {
        "message": "Updated message"
      }
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "status": "Active",
  "updated_at": "2025-11-12T10:30:00Z",
  "message": "Flow updated successfully"
}
```

---

### DELETE `/flows/{id}`
Delete a workflow flow.

**Response (200 OK):**
```json
{
  "message": "Flow deleted successfully"
}
```

---

### POST `/flows/{id}/activate`
Activate a flow (change status from Testing/Draft to Active).

**Response (200 OK):**
```json
{
  "id": "uuid",
  "status": "Active",
  "message": "Flow activated successfully"
}
```

---

### POST `/flows/{id}/deactivate`
Deactivate a flow (change status to Disabled).

**Response (200 OK):**
```json
{
  "id": "uuid",
  "status": "Disabled",
  "message": "Flow deactivated successfully"
}
```

---

### GET `/flows/{id}/executions`
Get execution history for a flow.

**Query Parameters:**
- `page` (integer): Page number
- `limit` (integer): Items per page
- `status` (string): Filter by execution status (success|failed|pending)

**Response (200 OK):**
```json
{
  "executions": [
    {
      "id": "uuid",
      "flow_id": "uuid",
      "status": "success",
      "trigger_data": {
        "contact_id": "uuid",
        "contact_name": "LUIS ZAPATA"
      },
      "started_at": "2025-11-12T10:15:00Z",
      "completed_at": "2025-11-12T10:15:03Z",
      "duration": "3.2s",
      "actions_completed": 5,
      "actions_failed": 0,
      "logs": [
        {
          "action": "send_message",
          "status": "success",
          "timestamp": "2025-11-12T10:15:01Z",
          "message": "Message sent successfully"
        }
      ]
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 25,
    "total_items": 1247
  }
}
```

---

### GET `/flows/stats`
Get workflow statistics.

**Response (200 OK):**
```json
{
  "total_flows": 12,
  "active_flows": 8,
  "disabled_flows": 2,
  "testing_flows": 2,
  "total_executions_today": 342,
  "total_executions_this_month": 8947,
  "avg_success_rate": 96.1,
  "most_used_triggers": [
    {
      "type": "contact_created",
      "count": 5
    },
    {
      "type": "message_received",
      "count": 3
    }
  ]
}
```

---

## Dashboard & Analytics

### GET `/dashboard/overview`
Get dashboard overview with key metrics across all modules.

**Response (200 OK):**
```json
{
  "contacts": {
    "total": 2476,
    "new_this_month": 1087,
    "active": 90,
    "growth_rate": 12.5
  },
  "deals": {
    "total_value": 48000,
    "active_deals": 6,
    "win_rate": 75,
    "avg_deal_size": 8000
  },
  "communications": {
    "active_chats": 70,
    "unread": 8,
    "avg_response_time": "5m",
    "messages_today": 247
  },
  "campaigns": {
    "active": 3,
    "total": 21,
    "messages_sent_this_month": 15847,
    "avg_open_rate": 76.2
  },
  "tickets": {
    "open": 245,
    "in_progress": 86,
    "avg_resolution_time": "4h 23m",
    "resolved_today": 12
  },
  "workflows": {
    "active": 8,
    "executions_today": 342,
    "success_rate": 96.1
  }
}
```

---

### GET `/dashboard/activity-feed`
Get recent activity feed across the system.

**Query Parameters:**
- `limit` (integer, default: 50): Number of activities
- `types` (string): Filter by activity types (comma-separated)

**Response (200 OK):**
```json
{
  "activities": [
    {
      "id": "uuid",
      "type": "contact_created",
      "title": "New contact created",
      "description": "MATÍAS CASTRO was added as a Lead",
      "user": {
        "id": "uuid",
        "name": "María García"
      },
      "timestamp": "2025-11-12T10:30:00Z",
      "metadata": {
        "contact_id": "uuid",
        "contact_name": "MATÍAS CASTRO"
      }
    },
    {
      "id": "uuid",
      "type": "ticket_resolved",
      "title": "Ticket resolved",
      "description": "TICK-2024-045 was marked as resolved",
      "user": {
        "id": "uuid",
        "name": "Juan Pérez"
      },
      "timestamp": "2025-11-12T10:25:00Z",
      "metadata": {
        "ticket_id": "uuid",
        "ticket_number": "TICK-2024-045"
      }
    },
    {
      "id": "uuid",
      "type": "campaign_completed",
      "title": "Campaign completed",
      "description": "Confirmacion Punta campaign finished with 79.7% open rate",
      "timestamp": "2025-11-12T10:15:00Z",
      "metadata": {
        "campaign_id": "uuid",
        "campaign_name": "Confirmacion Punta"
      }
    }
  ]
}
```

---

### GET `/dashboard/analytics/trends`
Get trend analytics over time.

**Query Parameters:**
- `metric` (string): Metric to analyze (contacts|deals|tickets|messages|campaigns)
- `period` (string): Time period (day|week|month|quarter|year)
- `start_date` (string): ISO date
- `end_date` (string): ISO date

**Response (200 OK):**
```json
{
  "metric": "contacts",
  "period": "week",
  "data_points": [
    {
      "date": "2025-11-05",
      "value": 142,
      "label": "Lunes"
    },
    {
      "date": "2025-11-06",
      "value": 168,
      "label": "Martes"
    },
    {
      "date": "2025-11-07",
      "value": 187,
      "label": "Miércoles"
    },
    {
      "date": "2025-11-08",
      "value": 195,
      "label": "Jueves"
    },
    {
      "date": "2025-11-09",
      "value": 178,
      "label": "Viernes"
    },
    {
      "date": "2025-11-10",
      "value": 89,
      "label": "Sábado"
    },
    {
      "date": "2025-11-11",
      "value": 128,
      "label": "Domingo"
    }
  ],
  "summary": {
    "total": 1087,
    "avg_per_day": 155.3,
    "peak_day": "2025-11-08",
    "peak_value": 195,
    "trend": "up",
    "change_percentage": 12.5
  }
}
```

---

## Data Models

### Contact Model
```typescript
{
  id: string (UUID)
  name: string (required)
  email: string | null
  phone: string | null
  company: string | null
  type: "Lead" | "Customer" | "Partner" | "Vendor" (required, default: "Lead")
  tags: string[]
  custom_fields: Record<string, any>
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
}
```

### Deal Model
```typescript
{
  id: string (UUID)
  title: string (required)
  company: string | null
  contact_id: string (UUID, foreign key)
  value: number (required)
  currency: string (default: "USD")
  stage: "qualified" | "proposal" | "negotiation" | "closed" | "lost" (required)
  probability: number (0-100)
  expected_close_date: ISO 8601 date | null
  assigned_to: string (UUID, user foreign key) | null
  tags: string[]
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
  closed_at: ISO 8601 timestamp | null
}
```

### Conversation Model
```typescript
{
  id: string (UUID)
  contact_id: string (UUID, foreign key, required)
  channel: "WhatsApp" | "Email" | "SMS" | "Instagram" | "Telegram" (required)
  status: "active" | "archived" | "closed"
  unread_count: number
  last_message_at: ISO 8601 timestamp
  tags: string[]
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
}
```

### Message Model
```typescript
{
  id: string (UUID)
  conversation_id: string (UUID, foreign key, required)
  content: string (required)
  sender: "agent" | "contact" | "system" (required)
  sender_id: string (UUID) | null
  sender_name: string | null
  type: "text" | "image" | "video" | "audio" | "file" | "system_note"
  status: "sent" | "delivered" | "read" | "failed"
  attachments: Attachment[]
  timestamp: ISO 8601 timestamp
}
```

### Campaign Model
```typescript
{
  id: string (UUID)
  name: string (required)
  type: string (required, e.g., "Express Campaign", "Drip Campaign")
  description: string | null
  status: "Active" | "Paused" | "Completed" | "Draft" (required)
  channel: "WhatsApp" | "Email" | "SMS" (required)
  template_id: string (UUID) | null
  target_audience: {
    contact_filter: Record<string, any>
  }
  schedule: {
    send_at: ISO 8601 timestamp | null
    timezone: string
  }
  metrics: {
    sent: number
    delivered: number
    failed: number
    opened: number
    clicked: number
    conversion_rate: number
  }
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
}
```

### Ticket Model
```typescript
{
  id: string (UUID)
  ticket_number: string (required, unique, auto-generated)
  subject: string (required)
  description: string | null
  customer_id: string (UUID, foreign key to Contact, required)
  status: "Open" | "In Progress" | "Resolved" | "Closed" (required)
  priority: "High" | "Medium" | "Low" (required)
  category: string | null
  assigned_to: string (UUID, user foreign key) | null
  due_date: ISO 8601 timestamp | null
  tags: string[]
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
  resolved_at: ISO 8601 timestamp | null
}
```

### Workflow (Flow) Model
```typescript
{
  id: string (UUID)
  name: string (required)
  description: string | null
  status: "Active" | "Disabled" | "Testing" | "Draft" (required)
  trigger: {
    type: string (e.g., "contact_created", "message_received", "ticket_created")
    conditions: Record<string, any>
  }
  actions: WorkflowAction[]
  created_by: string (UUID, user foreign key)
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
}
```

### WorkflowAction Model
```typescript
{
  id: string
  type: string (e.g., "send_message", "create_ticket", "delay", "conditional", "add_tag")
  config: Record<string, any>
  position: number
}
```

---

## AI Agent Engine Integration

### Webhook Events
The Moio Platform can send webhooks to the AI Agent Engine for automated processing and responses.

#### POST `/webhooks/ai-agent` (Receive from Platform)
Platform sends events to AI Agent for processing.

**Event Types:**
- `message.received` - New message from contact
- `ticket.created` - New support ticket created
- `contact.created` - New contact added
- `campaign.response` - Response to campaign message

**Webhook Payload Example:**
```json
{
  "event": "message.received",
  "timestamp": "2025-11-12T10:30:00Z",
  "data": {
    "conversation_id": "uuid",
    "message_id": "uuid",
    "contact": {
      "id": "uuid",
      "name": "LUIS ZAPATA",
      "phone": "+59892637130"
    },
    "message": {
      "content": "Hola, quiero confirmar mi entrevista",
      "channel": "WhatsApp",
      "timestamp": "2025-11-12T10:30:00Z"
    }
  }
}
```

---

### POST `/ai-agent/process`
Send data to AI agent for processing and get automated response.

**Request Body:**
```json
{
  "type": "message_analysis",
  "data": {
    "conversation_id": "uuid",
    "message": "Hola, quiero confirmar mi entrevista para mañana",
    "context": {
      "contact_name": "LUIS ZAPATA",
      "contact_type": "Lead",
      "previous_messages": []
    }
  }
}
```

**Response (200 OK):**
```json
{
  "analysis": {
    "intent": "confirmation",
    "sentiment": "positive",
    "entities": {
      "date": "tomorrow",
      "event_type": "interview"
    },
    "confidence": 0.95
  },
  "suggested_response": "Perfecto Luis! Tu entrevista está confirmada para mañana. Te esperamos.",
  "suggested_actions": [
    {
      "type": "update_contact",
      "data": {
        "tags": ["confirmed"]
      }
    },
    {
      "type": "create_calendar_event",
      "data": {
        "title": "Entrevista - Luis Zapata",
        "date": "2025-11-13T11:00:00Z"
      }
    }
  ]
}
```

---

### POST `/ai-agent/generate-summary`
Generate AI summary of conversation or ticket.

**Request Body:**
```json
{
  "type": "conversation",
  "id": "uuid",
  "messages": [
    {
      "content": "Hola, quiero información sobre el puesto",
      "sender": "contact"
    },
    {
      "content": "Claro! El puesto es para la zafra 2025-2026...",
      "sender": "agent"
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "summary": "El contacto solicitó información sobre el puesto de trabajo para la zafra 2025-2026. Se le brindó información completa y mostró interés en participar.",
  "sentiment": "positive",
  "next_steps": ["Enviar confirmación de entrevista", "Agregar a lista de candidatos"],
  "tags_suggested": ["interested", "zafra-2025"]
}
```

---

## Technical Specifications

### HTTP Status Codes

**Success Codes:**
- `200 OK` - Successful GET, PATCH, DELETE requests
- `201 Created` - Successful POST request creating a resource
- `204 No Content` - Successful request with no response body

**Client Error Codes:**
- `400 Bad Request` - Invalid request body or parameters
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `409 Conflict` - Resource conflict (e.g., duplicate email)
- `422 Unprocessable Entity` - Validation errors
- `429 Too Many Requests` - Rate limit exceeded

**Server Error Codes:**
- `500 Internal Server Error` - Unexpected server error
- `503 Service Unavailable` - Service temporarily unavailable

---

### Error Response Format

All error responses follow this structure:

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "details": {
    "field": "Specific field error"
  },
  "request_id": "uuid"
}
```

**Example Validation Error (422):**
```json
{
  "error": "validation_error",
  "message": "Validation failed",
  "details": {
    "email": "Invalid email format",
    "phone": "Phone number is required"
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### Pagination

All list endpoints support pagination with consistent parameters:

**Request Parameters:**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 50, max: 100): Items per page

**Response Format:**
```json
{
  "data": [...],
  "pagination": {
    "current_page": 1,
    "total_pages": 10,
    "total_items": 500,
    "items_per_page": 50,
    "has_next": true,
    "has_previous": false
  }
}
```

---

### Rate Limiting

API requests are rate-limited to ensure fair usage:

- **Authenticated requests:** 1000 requests per hour per user
- **Bulk operations:** 100 requests per hour
- **Webhook callbacks:** 5000 requests per hour

**Rate Limit Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1699876543
```

**Rate Limit Exceeded Response (429):**
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please try again later.",
  "retry_after": 3600
}
```

---

### Filtering & Searching

List endpoints support flexible filtering:

**Common Filter Parameters:**
- `search` - Full-text search across multiple fields
- `tags` - Filter by tags (comma-separated)
- `created_after` - ISO timestamp
- `created_before` - ISO timestamp
- `updated_after` - ISO timestamp
- `updated_before` - ISO timestamp

**Example:**
```
GET /contacts?search=zapata&tags=vip,priority&created_after=2025-11-01T00:00:00Z
```

---

### Sorting

Use `sort_by` and `order` parameters:

```
GET /contacts?sort_by=name&order=asc
GET /tickets?sort_by=priority&order=desc
```

Common sortable fields: `name`, `created_at`, `updated_at`, `priority`, `status`

---

### API Versioning

The API uses URL-based versioning:

```
https://api.moiodigital.com/v1/contacts
https://api.moiodigital.com/v2/contacts (future)
```

Breaking changes will result in a new version number. Non-breaking changes (adding fields, new endpoints) will not increment the version.

---

### WebSocket Support (Optional)

For real-time updates, connect to WebSocket endpoint:

```
wss://api.moiodigital.com/v1/ws?token={access_token}
```

**Subscribe to Events:**
```json
{
  "action": "subscribe",
  "channels": ["conversations", "tickets", "campaigns"]
}
```

**Receive Real-time Updates:**
```json
{
  "event": "message.received",
  "channel": "conversations",
  "data": {
    "conversation_id": "uuid",
    "message": {...}
  },
  "timestamp": "2025-11-12T10:30:00Z"
}
```

---

### Security Best Practices

1. **HTTPS Only** - All API requests must use HTTPS
2. **JWT Token Storage** - Store tokens securely (HttpOnly cookies or secure storage)
3. **Token Expiration** - Access tokens expire in 1 hour, refresh tokens in 30 days
4. **CORS** - Configure allowed origins for browser-based requests
5. **Input Validation** - All input is validated and sanitized server-side
6. **SQL Injection Protection** - Django ORM prevents SQL injection
7. **XSS Protection** - All output is escaped by default

---

### File Uploads

**Endpoint:** `POST /uploads`

**Request (multipart/form-data):**
```
file: (binary data)
type: image|document|video|audio
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "url": "https://cdn.moiodigital.com/files/abc123.jpg",
  "filename": "image.jpg",
  "size": 2048576,
  "mime_type": "image/jpeg",
  "uploaded_at": "2025-11-12T10:30:00Z"
}
```

**Limits:**
- Max file size: 50MB
- Allowed types: jpg, png, pdf, docx, xlsx, mp4, mp3, wav
- Files are stored in CDN with secure URLs

---

## Next Steps for Backend Developer

1. **Set up Django project** with Django REST Framework
2. **Implement authentication** using JWT (djangorestframework-simplejwt)
3. **Create data models** based on the Data Models section
4. **Build API endpoints** following this specification
5. **Implement AI Agent integration** for automated processing
6. **Set up WebSocket** support for real-time updates (Django Channels)
7. **Configure integrations** (WhatsApp Business API, OpenAI, etc.)
8. **Add comprehensive testing** (unit tests, integration tests)
9. **Deploy** using Docker + PostgreSQL + Redis (for caching/websockets)
10. **Monitor** with logging and error tracking (Sentry)

---

## Contact & Support

For questions or clarifications about this API specification:
- **Email:** dev@moiodigital.com
- **Documentation:** https://docs.moiodigital.com
- **Status Page:** https://status.moiodigital.com

---

**Document Version:** 1.0  
**Last Updated:** November 12, 2025  
**Maintained by:** Moio Digital Services Development Team
