# Activities API Reference

The Activities API provides CRUD operations for managing activities (tasks, notes, ideas, events). All activities share the same underlying model with a `kind` field to distinguish types.

## Base URL

```
/api/v1/activities/
```

## Authentication

All endpoints require authentication via session or JWT token.

## Activity Kinds

| Kind | Description |
|------|-------------|
| `task` | Tasks with due dates, priorities, and status |
| `note` | Freeform notes with tags |
| `idea` | Ideas with impact scores and tags |
| `event` | Calendar events with start/end times |

## Activity Object

```json
{
  "id": "uuid",
  "title": "string",
  "kind": "task | note | idea | event",
  "kind_label": "Task | Note | Idea | Event",
  "type": "string | null",
  "content": {},
  "source": "string | null",
  "visibility": "public | private",
  "visibility_label": "Public | Private",
  "user_id": "uuid | null",
  "created_at": "ISO 8601 datetime"
}
```

### Content Schemas by Kind

#### Task Content
```json
{
  "description": "Detailed description",
  "due_date": "ISO 8601 datetime",
  "priority": 1-5,
  "status": "open | in_progress | done"
}
```

#### Note Content
```json
{
  "body": "Note content",
  "tags": ["tag1", "tag2"]
}
```

#### Idea Content
```json
{
  "body": "Idea description",
  "impact": 1-10,
  "tags": ["tag1", "tag2"]
}
```

#### Event Content
```json
{
  "start": "ISO 8601 datetime",
  "end": "ISO 8601 datetime",
  "location": "string | null",
  "participants": ["user_id1", "user_id2"]
}
```

---

## Endpoints

### List Activities

```
GET /api/v1/activities/
```

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `kind` | string | Filter by kind: `task`, `note`, `idea`, `event` |
| `visibility` | string | Filter by visibility: `public`, `private` |
| `search` | string | Search in title and source |
| `sort_by` | string | Sort field: `created_at`, `title`, `kind`, `visibility` (default: `created_at`) |
| `order` | string | Sort order: `asc`, `desc` (default: `desc`) |
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 20, max: 100) |

#### Response

```json
{
  "activities": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Review Q4 Report",
      "kind": "task",
      "kind_label": "Task",
      "type": null,
      "content": {
        "description": "Review and approve the quarterly report",
        "due_date": "2025-12-20T17:00:00Z",
        "priority": 2,
        "status": "open"
      },
      "source": null,
      "visibility": "public",
      "visibility_label": "Public",
      "user_id": "123e4567-e89b-12d3-a456-426614174000",
      "created_at": "2025-12-14T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 45,
    "total_pages": 3
  }
}
```

#### Examples

```bash
# List all tasks
GET /api/v1/activities/?kind=task

# Search notes
GET /api/v1/activities/?kind=note&search=meeting

# List public ideas sorted by title
GET /api/v1/activities/?kind=idea&visibility=public&sort_by=title&order=asc
```

---

### Create Activity

```
POST /api/v1/activities/
```

#### Request Body

```json
{
  "title": "string (required)",
  "kind": "task | note | idea | event (default: note)",
  "type": "string (optional)",
  "content": {},
  "source": "string (optional)",
  "visibility": "public | private (default: public)"
}
```

#### Examples

##### Create a Task
```json
{
  "title": "Complete project documentation",
  "kind": "task",
  "content": {
    "description": "Write comprehensive API documentation",
    "due_date": "2025-12-31T23:59:59Z",
    "priority": 2,
    "status": "open"
  }
}
```

##### Create a Note
```json
{
  "title": "Meeting Notes - Dec 14",
  "kind": "note",
  "content": {
    "body": "Discussed roadmap for Q1 2026...",
    "tags": ["meeting", "planning", "q1"]
  }
}
```

##### Create an Idea
```json
{
  "title": "AI-powered search feature",
  "kind": "idea",
  "content": {
    "body": "Implement semantic search using embeddings",
    "impact": 8,
    "tags": ["ai", "search", "enhancement"]
  }
}
```

##### Create an Event
```json
{
  "title": "Team Standup",
  "kind": "event",
  "content": {
    "start": "2025-12-15T09:00:00Z",
    "end": "2025-12-15T09:30:00Z",
    "location": "Conference Room A",
    "participants": []
  }
}
```

#### Response

Returns the created activity object with `201 Created` status.

---

### Get Activity

```
GET /api/v1/activities/{activity_id}/
```

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `activity_id` | UUID | The activity ID |

#### Response

Returns the activity object or `404 Not Found` if not found.

---

### Update Activity

```
PATCH /api/v1/activities/{activity_id}/
```

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `activity_id` | UUID | The activity ID |

#### Request Body

All fields are optional. Only provided fields will be updated.

```json
{
  "title": "string",
  "kind": "task | note | idea | event",
  "type": "string | null",
  "content": {},
  "source": "string",
  "visibility": "public | private"
}
```

#### Example: Update Task Status

```json
{
  "content": {
    "description": "Write comprehensive API documentation",
    "due_date": "2025-12-31T23:59:59Z",
    "priority": 2,
    "status": "done"
  }
}
```

#### Response

Returns the updated activity object.

---

### Delete Activity

```
DELETE /api/v1/activities/{activity_id}/
```

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `activity_id` | UUID | The activity ID |

#### Response

```json
{
  "message": "Activity deleted successfully"
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "error": "tenant_required",
  "message": "User must belong to a tenant"
}
```

### 404 Not Found
```json
{
  "error": "activity_not_found",
  "message": "Activity not found"
}
```

---

## Agent Tool Functions

The following agent tools are available for creating and querying activities:

### Create Functions
- `create_task(title, description, due_date, priority, status)` - Create a task
- `create_note(title, body, tags)` - Create a note
- `create_idea(title, body, impact, tags)` - Create an idea
- `create_event(title, start, end, location, participants)` - Create an event

All create functions return:
```json
{
  "<kind>_created": "true",
  "activity_id": "uuid",
  "title": "...",
  ...
}
```

### Query Functions
- `list_tasks(status, due_before, due_after, priority_min, priority_max, search, limit)` - List tasks
- `search_notes(tag, search, limit)` - Search notes
- `list_ideas(min_impact, tag, search, limit)` - List ideas
- `upcoming_events(start_after, limit)` - List upcoming events

All query functions return:
```json
{
  "<kind>s": [...],
  "count": N
}
```
