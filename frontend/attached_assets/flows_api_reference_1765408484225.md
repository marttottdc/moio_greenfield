# Flows API Reference

Base URL: `/api/flows/`

All endpoints require authentication via session or JWT token.

---

## Flow Lifecycle Overview

```
Draft (editable) ──[publish]──▶ Published Active (locked, receives events)
     │                                    │
     │                                    ▼
     │                         Published Inactive (locked, logs only)
     │                                    │
     └──────────[new-version]◀────────────┘
```

### Flow States
- **Draft**: Editable, can be previewed. Not receiving production events unless "armed".
- **Published Active**: Locked for editing, receives production events. `flow.is_enabled = true`
- **Published Inactive**: Locked for editing, historical logs only. Rollback candidate.

### Version States
- **is_published: false**: Draft version, editable
- **is_published: true**: Published version, locked
- **preview_armed: true**: Draft temporarily receiving events for live testing

---

## Endpoints

### Flow CRUD

#### List Flows
```
GET /api/flows/
```

**Response:**
```json
{
  "ok": true,
  "flows": [
    {
      "id": "uuid",
      "name": "My Flow",
      "description": "...",
      "status": "active|inactive|draft",
      "is_enabled": true,
      "created_at": "2025-12-10T12:00:00Z",
      "updated_at": "2025-12-10T12:00:00Z",
      "created_by": { "id": "uuid", "name": "John Doe" },
      "current_version_id": "uuid",
      "latest_version": { ... },
      "published_version": { ... }
    }
  ]
}
```

#### Get Flow Detail
```
GET /api/flows/{flow_id}/
```

**Query Parameters:**
- `include_graph=true` - Include full graph data

**Response:**
```json
{
  "ok": true,
  "flow": { ... },
  "version": { ... },
  "graph": { ... },
  "endpoints": {
    "detail": "/api/flows/{id}/",
    "save": "/api/flows/{id}/save/",
    "validate": "/api/flows/{id}/validate/",
    "publish": "/api/flows/{id}/publish/",
    "preview": "/api/flows/{id}/preview/"
  }
}
```

---

### Graph Operations

#### Save Graph (Draft Only)
```
POST /api/flows/{flow_id}/save/
Content-Type: application/json

{
  "graph": {
    "nodes": [...],
    "edges": [...],
    "viewport": { "x": 0, "y": 0, "zoom": 1 }
  }
}
```

**Response:**
```json
{
  "ok": true,
  "version": {
    "id": "uuid",
    "major": 1,
    "minor": 2,
    "label": "v1.2",
    "is_published": false,
    "is_editable": true
  }
}
```

**Errors:**
- `400` - Version is published (not editable)
- `400` - Validation errors

#### Validate Graph
```
POST /api/flows/{flow_id}/validate/
Content-Type: application/json

{
  "graph": { ... }
}
```

**Response:**
```json
{
  "ok": true,
  "valid": true,
  "errors": [],
  "warnings": []
}
```

---

### Version Management

#### List Versions
```
GET /api/flows/{flow_id}/versions/
```

**Query Parameters:**
- `include_graph=true` - Include full graph data for each version

**Response:**
```json
{
  "ok": true,
  "versions": [
    {
      "id": "uuid",
      "flow_id": "uuid",
      "major": 2,
      "minor": 0,
      "label": "v2.0",
      "is_published": true,
      "is_active": true,
      "is_editable": false,
      "preview_armed": false,
      "preview_armed_at": null,
      "notes": "Production release",
      "created_at": "2025-12-10T12:00:00Z"
    },
    {
      "id": "uuid",
      "major": 1,
      "minor": 3,
      "label": "v1.3",
      "is_published": false,
      "is_active": false,
      "is_editable": true,
      "preview_armed": true,
      "preview_armed_at": "2025-12-10T11:00:00Z",
      "notes": "Work in progress"
    }
  ]
}
```

#### Get Version Detail
```
GET /api/flows/{flow_id}/versions/{version_id}/
```

**Response:**
```json
{
  "ok": true,
  "version": {
    "id": "uuid",
    "graph": { "nodes": [...], "edges": [...] },
    ...
  }
}
```

#### Publish Version
```
POST /api/flows/{flow_id}/publish/
Content-Type: application/json

{
  "graph": { ... }  // Optional: publish with new graph data
}
```

**Response:**
```json
{
  "ok": true,
  "version": {
    "id": "uuid",
    "label": "v2.0",
    "is_published": true
  },
  "flow": { ... }
}
```

**Notes:**
- Publishing locks the version (becomes non-editable)
- Increments major version number
- Previous published version becomes inactive

#### Create New Version (Clone)
```
POST /api/flows/{flow_id}/new-version/
```

**Response:**
```json
{
  "ok": true,
  "version": {
    "id": "uuid",
    "major": 3,
    "minor": 0,
    "label": "v3.0",
    "is_published": false,
    "is_editable": true
  },
  "message": "Created new draft v3.0 from published version."
}
```

**Notes:**
- Clones the currently active published version
- Creates a new draft that can be edited independently
- Multiple parallel drafts are supported

---

### Flow Activation

#### Toggle Flow Active Status
```
POST /api/flows/{flow_id}/toggle-active/
```

**Response:**
```json
{
  "ok": true,
  "flow": {
    "id": "uuid",
    "is_enabled": false,
    ...
  },
  "message": "Flow deactivated. No longer receives events."
}
```

**Notes:**
- When `is_enabled = false`, published flow stops receiving production events
- Useful for temporarily disabling a flow without unpublishing

---

### Preview & Testing

#### Start Preview Run
```
POST /api/flows/{flow_id}/preview/
Content-Type: application/json

{
  "run_id": "uuid",         // Optional: custom run ID
  "payload": { ... },       // Trigger payload to test with
  "graph": { ... }          // Optional: test unsaved graph changes
}
```

**Response:**
```json
{
  "ok": true,
  "run_id": "uuid",
  "execution": {
    "id": "uuid",
    "status": "pending|running|success|failed",
    "started_at": "2025-12-10T12:00:00Z",
    "timeline": []
  },
  "ws_url": "/ws/flows/{flow_id}/preview/stream/"
}
```

#### Get Preview Status
```
GET /api/flows/{flow_id}/preview/{run_id}/
```

**Response:**
```json
{
  "ok": true,
  "execution": {
    "id": "uuid",
    "status": "success",
    "duration_ms": 1234,
    "timeline": [
      {
        "node_id": "node-1",
        "kind": "trigger_event",
        "name": "On Ticket Created",
        "status": "success",
        "started_at": "...",
        "finished_at": "...",
        "input": { ... },
        "output": { ... }
      }
    ]
  }
}
```

#### Arm Draft for Live Preview
```
POST /api/flows/{flow_id}/versions/{version_id}/arm/
```

**Response:**
```json
{
  "ok": true,
  "version": {
    "preview_armed": true,
    "preview_armed_at": "2025-12-10T12:00:00Z"
  },
  "message": "Preview armed. This draft will now receive matching events."
}
```

**Notes:**
- Only drafts can be armed (not published versions)
- Armed draft receives real events matching its trigger configuration
- Use for live testing before publishing
- Events are routed to BOTH active published flow AND armed draft

#### Disarm Draft
```
POST /api/flows/{flow_id}/versions/{version_id}/disarm/
```

**Response:**
```json
{
  "ok": true,
  "version": {
    "preview_armed": false,
    "preview_armed_at": null
  },
  "message": "Preview disarmed. This draft will no longer receive events."
}
```

---

### Execution History

#### List Executions
```
GET /api/flows/{flow_id}/executions/
```

**Query Parameters:**
- `limit` (default: 50, max: 100)
- `offset` (default: 0)
- `status` - Filter by status: `pending|running|success|failed`
- `trigger_source` - Filter by source: `event|webhook|schedule|manual|preview`

**Response:**
```json
{
  "ok": true,
  "total": 150,
  "limit": 50,
  "offset": 0,
  "executions": [
    {
      "id": "uuid",
      "status": "success",
      "status_display": "Success",
      "duration_ms": 1234,
      "started_at": "2025-12-10T12:00:00Z",
      "completed_at": "2025-12-10T12:00:01Z",
      "input": { "event_type": "ticket.created", ... },
      "output": { ... },
      "error": {},
      "timeline": [...]
    }
  ]
}
```

#### Get Execution Detail
```
GET /api/flows/{flow_id}/executions/{execution_id}/
```

**Response:**
```json
{
  "ok": true,
  "execution": {
    "id": "uuid",
    "status": "success",
    "timeline": [
      {
        "node_id": "node-1",
        "kind": "trigger_event",
        "name": "On Ticket Created",
        "status": "success",
        "input": { ... },
        "output": { ... },
        "started_at": "...",
        "finished_at": "..."
      },
      {
        "node_id": "node-2",
        "kind": "action_send_message",
        "status": "success",
        ...
      }
    ]
  }
}
```

---

### Manual Execution

#### Trigger Manual Run
```
POST /api/flows/{flow_id}/manual-run/
Content-Type: application/json

{
  "payload": { ... }
}
```

**Response:**
```json
{
  "ok": true,
  "detail": { "triggered": true, "execution_id": "uuid" },
  "message": "Flow execution triggered successfully.",
  "level": "success"
}
```

---

### Event Definitions

#### List Available Events
```
GET /api/flows/events/
```

**Response:**
```json
{
  "ok": true,
  "events": [
    {
      "id": "uuid",
      "event_type": "ticket.created",
      "name": "Ticket Created",
      "description": "Fired when a new ticket is created",
      "category": "crm",
      "payload_schema": {
        "type": "object",
        "properties": {
          "ticket_id": { "type": "string" },
          "subject": { "type": "string" },
          "priority": { "type": "string" }
        }
      }
    },
    {
      "event_type": "ticket.updated",
      "name": "Ticket Updated",
      ...
    },
    {
      "event_type": "deal.stage_changed",
      "name": "Deal Stage Changed",
      ...
    }
  ]
}
```

#### Get Event Detail
```
GET /api/flows/events/{event_id}/
```

---

### Node Definitions

#### List Available Nodes
```
GET /api/flows/definitions/
```

**Response:**
```json
{
  "ok": true,
  "definitions": {
    "triggers": [
      {
        "kind": "trigger_event",
        "title": "Event Trigger",
        "description": "Triggered by system events",
        "category": "triggers",
        "config_schema": { ... },
        "ports": { "input": [], "output": ["default"] }
      },
      {
        "kind": "trigger_webhook",
        "title": "Webhook Trigger",
        ...
      }
    ],
    "actions": [...],
    "logic": [...],
    "outputs": [...]
  }
}
```

---

### Schedules

#### List Schedules
```
GET /api/flows/{flow_id}/schedules/
```

#### Create Schedule
```
POST /api/flows/{flow_id}/schedules/
Content-Type: application/json

{
  "schedule_type": "cron|interval",
  "cron_expression": "0 9 * * *",  // For cron type
  "interval_seconds": 3600,         // For interval type
  "is_enabled": true,
  "payload": { ... }
}
```

#### Update Schedule
```
PUT /api/flows/{flow_id}/schedules/{schedule_id}/
```

#### Delete Schedule
```
DELETE /api/flows/{flow_id}/schedules/{schedule_id}/
```

#### Toggle Schedule
```
POST /api/flows/{flow_id}/schedules/{schedule_id}/toggle/
```

---

## WebSocket Endpoints

### Preview Stream
```
ws://{host}/ws/flows/{flow_id}/preview/stream/
```

**Messages Received:**
```json
{
  "type": "step_update",
  "step": {
    "node_id": "node-1",
    "status": "running|success|error",
    "output": { ... }
  }
}
```

```json
{
  "type": "run_complete",
  "execution": { ... }
}
```

---

## Error Responses

All endpoints return consistent error format:

```json
{
  "ok": false,
  "error": "Human-readable error message",
  "code": "ERROR_CODE"  // Optional
}
```

Common HTTP status codes:
- `400` - Bad request / validation error
- `401` - Authentication required
- `403` - Permission denied
- `404` - Resource not found
- `409` - Conflict (e.g., flow already running)

---

## Graph Schema

### Node Structure
```json
{
  "id": "unique-node-id",
  "kind": "trigger_event|action_send_message|logic_branch|...",
  "name": "Human readable name",
  "description": "Optional description",
  "position": { "x": 100, "y": 200 },
  "config": {
    // Kind-specific configuration
  }
}
```

### Edge Structure
```json
{
  "id": "unique-edge-id",
  "source": "source-node-id",
  "target": "target-node-id",
  "sourceHandle": "output-port-name",
  "targetHandle": "input-port-name"
}
```

### Common Node Kinds

#### Triggers
- `trigger_event` - Event-based trigger (ticket.created, deal.stage_changed, etc.)
- `trigger_webhook` - HTTP webhook trigger
- `trigger_schedule` - Time-based trigger
- `trigger_manual` - Manual execution trigger

#### Actions
- `action_send_message` - Send WhatsApp/Email/SMS
- `action_create_ticket` - Create CRM ticket
- `action_update_contact` - Update contact fields
- `action_http_request` - Make HTTP request
- `action_run_script` - Execute custom script

#### Logic
- `logic_branch` - Conditional branching
- `logic_condition` - If/else logic
- `logic_while` - Loop while condition
- `logic_delay` - Wait for duration

#### Outputs
- `output_event` - Emit system event
- `output_response` - Return response data

---

## Best Practices

1. **Always validate before publishing** - Call `/validate/` before `/publish/`
2. **Use preview for testing** - Test with realistic payloads before going live
3. **Arm drafts for integration testing** - Use arm/disarm for live event testing
4. **Monitor executions** - Check execution history for errors
5. **Use WebSocket for real-time updates** - Connect to preview stream during testing
