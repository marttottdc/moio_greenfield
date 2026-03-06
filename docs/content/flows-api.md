---
title: "Flows API"
slug: "flows-api"
category: "flows"
order: 2
status: "published"
summary: "- `GET /api/v1/flows/` - List flows - `POST /api/v1/flows/` - Create flow - `GET /api/v1/flows/{id}/` - Get flow detail - `PUT /api/v1/flows/{id}/` - Update flow - `DELETE /api/v1/flows/{id}/` - Delet"
tags: ["flows"]
---

## Overview

- `GET /api/v1/flows/` - List flows - `POST /api/v1/flows/` - Create flow - `GET /api/v1/flows/{id}/` - Get flow detail - `PUT /api/v1/flows/{id}/` - Update flow - `DELETE /api/v1/flows/{id}/` - Delet

# flows - Interfaces

## Public API Endpoints

### Flow CRUD
- `GET /api/v1/flows/` - List flows
- `POST /api/v1/flows/` - Create flow
- `GET /api/v1/flows/{id}/` - Get flow detail
- `PUT /api/v1/flows/{id}/` - Update flow
- `DELETE /api/v1/flows/{id}/` - Delete flow

### Flow Versions
- `GET /api/v1/flows/{id}/versions/` - List versions
- `POST /api/v1/flows/{id}/versions/` - Create version
- `POST /api/v1/flows/{id}/versions/{vid}/publish/` - Publish version
- `POST /api/v1/flows/{id}/versions/{vid}/arm/` - Arm for testing

### Flow Execution
- `POST /api/v1/flows/{id}/execute/` - Execute flow
- `POST /api/v1/flows/{id}/preview/` - Start preview execution
- `GET /api/v1/flows/{id}/executions/` - List executions

### Schedules
- `GET /api/v1/flows/{id}/schedules/` - List schedules
- `POST /api/v1/flows/{id}/schedules/` - Create schedule
- `DELETE /api/v1/flows/{id}/schedules/{sid}/` - Delete schedule

### Events
- `GET /api/v1/events/definitions/` - List event definitions
- `POST /api/v1/events/` - Manual event emission

### Scripts
- `GET /api/v1/scripts/` - List scripts
- `POST /api/v1/scripts/` - Create script
- `POST /api/v1/scripts/{id}/run/` - Execute script

## Events Emitted

### flow.execution_completed
Emitted after every flow execution.

```python
{
    "name": "flow.execution_completed",
    "tenant_id": str,
    "actor": {"type": "system", "id": "flows.tasks.execute_flow_sync"},
    "entity": {"type": "flow_execution", "id": str},
    "payload": {
        "flow_id": str,
        "execution_id": str,
        "status": str,  # "success" | "failed"
        "trigger_source": str,
        "execution_mode": str,  # "production" | "testing" | "preview"
        "sandbox": bool,
        "started_at": str,
        "completed_at": str,
        "duration_ms": int,
        "version_id": str,
        "trace_id": str | None,
        "input": dict,
        "output": dict,
        "error": dict,
        "execution": dict  # Full snapshot
    },
    "source": "flows"
}
```

## WebSocket Events

Via `WebSocketEventPublisher.publish_flow_preview_event()`:

### execution_started
```python
{"flow_id": str, "execution_id": str, "execution_mode": str}
```

### node_finished
```python
{
    "node_id": str,
    "node_name": str,
    "output": any,
    "step_index": int,
    "execution_mode": str
}
```

### node_error
```python
{
    "node_id": str,
    "node_name": str,
    "error": str,
    "step_index": int,
    "execution_mode": str
}
```

### execution_completed
```python
{
    "status": str,
    "duration_ms": int,
    "execution_id": str,
    "execution_mode": str
}
```

## Celery Tasks

### execute_flow
- **Queue**: `FLOWS_Q`
- **Input**: `flow_id`, `payload`, `trigger_source`, `trigger_metadata`, `version_id`, `sandbox`
- **Output**: Execution result dict

### preview_flow
- **Queue**: `FLOWS_Q`
- **Input**: `flow_id`, `run_id`, `trigger_payload`, `graph_payload`, `execution_id`
- **Side Effects**: WebSocket events for live preview

### execute_sandbox_preview
- **Queue**: `FLOWS_Q`
- **Purpose**: Armed draft testing with real events

### execute_scheduled_flow
- **Queue**: `FLOWS_Q`
- **Input**: `schedule_id`, `flow_id`, `tenant_id`
- **Triggered by**: Celery Beat

### execute_scheduled_task
- **Queue**: `FLOWS_Q`
- **Input**: `scheduled_task_id`, `tenant_id`
- **Purpose**: Generic task scheduling

## Input/Output Schemas

### FlowVersion Graph

```python
{
    "nodes": [
        {
            "id": str,
            "kind": str,  # Node type
            "label": str,
            "config": dict,  # Node-specific configuration
            "position": {"x": int, "y": int}
        }
    ],
    "edges": [
        {
            "id": str,
            "source": str,  # Source node ID
            "target": str,  # Target node ID
            "sourceHandle": str,
            "targetHandle": str
        }
    ]
}
```

### FlowSchedule

```python
{
    "id": UUID,
    "flow": UUID,
    "schedule_type": str,  # "cron" | "interval" | "one_off"
    "cron_expression": str | None,
    "interval_seconds": int | None,
    "timezone": str,
    "is_active": bool,
    "last_run_at": datetime | None
}
```

### FlowExecution

```python
{
    "id": UUID,
    "flow": UUID,
    "status": str,  # "pending" | "running" | "success" | "failed" | "cancelled"
    "trigger_source": str,
    "input_data": dict,
    "output_data": dict,
    "error_data": dict,
    "execution_context": {
        "graph_version": str,
        "version_id": str,
        "version_status": str,
        "status_log": [{"status": str, "at": str}],
        "trigger_source": str,
        "sandbox": bool,
        "execution_mode": str,
        "timeline": [dict]
    },
    "started_at": datetime,
    "completed_at": datetime | None,
    "duration_ms": int | None
}
```

### Data Lab node outputs

Node executors return the following shapes (all include `success: bool`; on failure, `error: str`).

- **datalab_ingest**: `file_id`, `filename`, `content_type`, `size`, `storage_key`
- **datalab_file_adapter**: `resultset_id`, `row_count`, `schema`
- **datalab_resultset_get**: `resultset_id`, `schema_json`, `row_count`, `is_json_object`, `preview_json`, `storage`, `storage_key`, `origin`
- **datalab_promote**: `dataset_id`, `version_number`, `row_count`
