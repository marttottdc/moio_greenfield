---
title: "Flows Error Handling"
slug: "flows-errors"
category: "flows"
order: 6
status: "published"
summary: "- **Flow.DoesNotExist**: Returns `{\"error\": \"Flow not found: {id}\"}` - **Version not found**: Returns `{\"error\": \"Version not found: {id}\"}` - **No executable version**: Returns `{\"error\": \"No executa"
tags: ["flows"]
---

## Overview

- **Flow.DoesNotExist**: Returns `{"error": "Flow not found: {id}"}` - **Version not found**: Returns `{"error": "Version not found: {id}"}` - **No executable version**: Returns `{"error": "No executa

# flows - Failures

## Explicit Error Handling

### execute_flow_sync
- **Flow.DoesNotExist**: Returns `{"error": "Flow not found: {id}"}`
- **Version not found**: Returns `{"error": "Version not found: {id}"}`
- **No executable version**: Returns `{"error": "No executable version found"}`
- **Draft version**: Returns `{"error": "Draft versions cannot be executed"}`
- **Execution exception**: 
  - FlowExecution.status = "failed"
  - FlowExecution.error_data = {message, type}
  - Flow.last_execution_status = "failed"
  - Returns `{"error": str}`

### preview_flow
- **Flow.DoesNotExist**: Log error, return
- **No graph available**: WebSocket: error event
- **Graph validation error**: 
  - FlowExecution.status = "failed"
  - WebSocket: error event
- **Schema validation error**: Same as graph validation
- **Runtime exception**: 
  - FlowExecution.status = "failed"
  - Timeline preserved

### execute_scheduled_flow
- **FlowSchedule.DoesNotExist**: Returns `{"error": "..."}`
- **Schedule inactive**: Returns `{"error": "..."}`
- Delegates to execute_flow_sync for execution errors

### execute_scheduled_task
- **ScheduledTask.DoesNotExist**: Returns `{"error": "..."}`
- **Task not in registry**: Marks execution failed
- **Dispatch exception**: Marks execution failed with traceback

## Expected Failure Modes

### Node Execution Failures
- HTTP request timeout/error
- CRM operation failure
- Script execution error
- Expression evaluation error

### Graph Validation Failures
- Invalid node structure
- Missing required config
- Invalid edge connections
- Schema mismatch (webhook trigger)

### Schedule Failures
- Invalid cron expression
- Celery Beat registration failure
- Schedule conflict

## Recovery Mechanisms

### Automatic Recovery
- FlowExecution preserves timeline on failure
- Error details captured in error_data
- WebSocket events sent even on failure
- Event emission wrapped in try/except (non-blocking)

### Manual Recovery
- Re-execute flow with same payload
- Check FlowExecution.error_data for details
- Review timeline for partial execution state
- Fix graph and create new version

### Execution Tracking
- Every execution logged regardless of outcome
- Timeline shows node-by-node progress
- Status log tracks state transitions
- Duration calculated even on failure
