---
title: "Moio Platform API"
slug: "moio-platform-api"
category: "api-reference"
order: 2
status: "published"
summary: "- `GET /api/v1/health/` - System health check"
tags: ["moio_platform"]
---

## Overview

- `GET /api/v1/health/` - System health check

# moio_platform - Interfaces

## Public Endpoints

### Health Check

- `GET /api/v1/health/` - System health check

### API Documentation

- `GET /api/schema/` - OpenAPI schema
- `GET /api/docs/` - Swagger UI
- `GET /api/redoc/` - ReDoc

### Error Handlers

- handler400 - Bad Request
- handler403 - Forbidden
- handler404 - Not Found
- handler500 - Internal Server Error

## Events Emitted

Event emission via `moio_platform.core.events.emit_event()`:

```python
emit_event(
    name="entity.action",
    tenant_id=uuid,
    actor={"type": "user|system|service", "id": "uuid"},
    entity={"type": "entity_type", "id": "uuid"},
    payload={...},
    source="source_identifier",
)
```

## Events Consumed

Event routing via `moio_platform.core.events.router`.

## Input/Output Schemas

Event payload schemas defined in `moio_platform.core.events.schemas`.
