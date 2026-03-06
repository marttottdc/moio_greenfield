---
title: "Flows Lifecycle"
slug: "flows-lifecycle"
category: "flows"
order: 3
status: "published"
summary: "- App config registered via `FlowsConfig` - Signals imported on ready - Event definitions seeded via migrations"
tags: ["flows"]
---

## Overview

- App config registered via `FlowsConfig` - Signals imported on ready - Event definitions seeded via migrations

# flows - Lifecycle

## Startup Behavior

- App config registered via `FlowsConfig`
- Signals imported on ready
- Event definitions seeded via migrations

## Runtime Behavior

### FlowVersion State Machine (FSM)

```
DRAFT
  │
  ├── Edit graph
  │
  ├── arm() [Testing mode]
  │   └── Sets preview_armed = True
  │
  ▼
TESTING
  │
  ├── Receives events in sandbox mode
  ├── External actions simulated
  │
  ├── publish()
  │
  ▼
PUBLISHED
  │
  ├── Receives events in production mode
  ├── External actions executed
  │
  ├── New version published → auto-archive
  │
  ▼
ARCHIVED
```

### Flow Execution Flow

```
execute_flow_sync(flow_id, payload, ...)
  │
  ├── Load Flow
  ├── Resolve version (specific or published/testing)
  │   └── Draft versions rejected
  │
  ├── Determine sandbox mode (testing=sandbox, published=production)
  │
  ├── Create FlowExecution record (status=running)
  │
  ├── Validate and load graph
  │
  ├── Create FlowRun instance
  │   ├── Setup step callback for timeline/WebSocket
  │   └── Set sandbox flag
  │
  ├── run.execute()
  │   │
  │   ├── Find trigger node
  │   ├── Execute node sequence:
  │   │   ├── Load node config
  │   │   ├── Get executor for node kind
  │   │   ├── Execute with context
  │   │   ├── Call on_step callback
  │   │   └── Determine next node(s)
  │   │
  │   └── Return result snapshot
  │
  ├── Update FlowExecution (status, output, timeline)
  ├── Update Flow stats (execution_count, last_executed_at)
  │
  ├── Emit flow.execution_completed event
  │
  └── Return result
```

### Schedule Execution Flow

```
Celery Beat (periodic task)
  │
  ├── execute_scheduled_flow(schedule_id, flow_id, tenant_id)
  │   │
  │   ├── Load FlowSchedule
  │   ├── Check is_active
  │   ├── Update last_run_at
  │   │
  │   ├── execute_flow_sync(flow_id, trigger_source="schedule")
  │   │
  │   └── If one_off: deactivate schedule
  │
  └── ScheduleService.delete_schedule() [for one_off]
```

### Preview Execution Flow

```
preview_flow(flow_id, run_id, trigger_payload, ...)
  │
  ├── Load Flow
  ├── Create/update FlowExecution (preview_active=True)
  │
  ├── WebSocket: stream_started
  │
  ├── Validate graph
  │   └── Schema validation for webhook triggers
  │
  ├── Execute with on_step callback:
  │   └── WebSocket: node_finished / node_error
  │
  ├── Update execution (timeline, status)
  │
  └── WebSocket: preview_completed
```

### Event Trigger Flow

```
Platform event emitted
  │
  ├── Match FlowSignalTriggers by event name
  │
  ├── For each matching trigger:
  │   │
  │   ├── If version status = TESTING:
  │   │   └── execute_sandbox_preview (simulated)
  │   │
  │   └── If version status = PUBLISHED:
  │       └── execute_flow_sync (production)
```

## Shutdown Behavior

- Schedule cleanup on flow/schedule deletion
- FlowExecution preserves history
- No graceful task cancellation
