---
title: "Flows Rules & Constraints"
slug: "flows-rules"
category: "flows"
order: 5
status: "published"
summary: "- Flow must have `tenant` (tenant-scoped) - Flow name unique per tenant - `execution_count` and stats are aggregate values"
tags: ["flows"]
---

## Overview

- Flow must have `tenant` (tenant-scoped) - Flow name unique per tenant - `execution_count` and stats are aggregate values

# flows - Invariants

## Data Integrity Rules

### Flow Rules
- Flow must have `tenant` (tenant-scoped)
- Flow name unique per tenant
- `execution_count` and stats are aggregate values

### FlowVersion Rules
- Version number auto-incremented per flow
- Only one version can be PUBLISHED at a time per flow
- Status transitions follow FSM rules
- Graph JSON validated against schema before save

### FlowExecution Rules
- Always linked to a Flow
- Status must be: pending, running, success, failed, cancelled
- `completed_at` set when status transitions to terminal state
- `duration_ms` calculated from start to completion

### FlowSchedule Rules
- Schedule type must be: cron, interval, one_off
- Cron expression required for cron type
- Interval seconds required for interval type
- One-off schedules auto-deactivate after execution

### FlowSignalTrigger Rules
- Event name must match EventDefinition
- Linked to specific FlowVersion

## Business Logic Constraints

### Version Execution Rules
- Draft versions cannot execute via webhooks/events
- Testing versions execute in sandbox mode
- Published versions execute in production mode
- Only one published version per flow

### Sandbox Mode Behavior
- External HTTP requests simulated
- WhatsApp messages not sent (logged)
- Email not sent (logged)
- CRM operations simulated
- All outputs returned as simulated

### Expression Evaluation
- Variable interpolation: `{{variable}}`
- Trigger data access: `trigger.payload.field`
- Step output access: `steps.node_id.output`

## Concurrency Controls

### Execution Isolation
- Each execution creates separate FlowExecution record
- No shared state between executions
- Timeline tracked per execution

### Version Locking
- Publishing creates new version, archives previous
- Testing version can coexist with published version
- Draft can be edited while other versions execute
