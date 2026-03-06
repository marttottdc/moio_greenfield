---
title: "Flows Overview"
slug: "flows-overview"
category: "flows"
order: 1
status: "published"
summary: "Visual workflow automation engine with node-based flow builder, multi-trigger support (webhooks, schedules, events), and sandbox execution mode for testing."
tags: ["flows"]
---

## Overview

Visual workflow automation engine with node-based flow builder, multi-trigger support (webhooks, schedules, events), and sandbox execution mode for testing.

## Form Components

Flow nodes expose a `form_component` hint for the frontend to pick the correct configuration form. Examples:

- `datalab_file_adapter`: `datalab-file-adapter-form`
- `datalab_promote`: `datalab-promote-form`
- `datalab_ingest`: `datalab-ingest-form`
- `datalab_resultset_get`: `datalab-resultset-get-form`
- `output_event`: `output-event-form`
- `output_task`: `output-task-form`
- `output_webhook_reply`: `output-webhook-reply-form`
- `output_agent`: `output-agent-form`
- `debug_logger`: `debug-logger-form`

These are UI hints only; backend validation remains authoritative for required fields.

# flows

## Responsibility

Visual workflow automation engine with node-based flow builder, multi-trigger support (webhooks, schedules, events), and sandbox execution mode for testing.

## What it Owns

- **Flow**: Workflow definitions with execution stats
- **FlowVersion**: Versioned flow graphs with FSM lifecycle (draft → testing → published → archived)
- **FlowExecution**: Execution logs with input/output, status, timeline
- **FlowSchedule**: Scheduled flow triggers (cron, interval, one-off)
- **FlowSignalTrigger**: Event-based flow triggers
- **FlowScript/FlowScriptVersion**: Python script nodes with versioning
- **FlowScriptRun/FlowScriptLog**: Script execution tracking
- **FlowAgentContext/FlowAgentTurn**: AI agent conversation context in flows
- **EventDefinition/EventLog**: Platform event system
- **ScheduledTask/TaskExecution**: Generic task scheduling

## Core Components

### Flow Runtime (`core/runtime.py`)
- `FlowRun`: Main execution engine
- Node-by-node execution with step callbacks
- Variable interpolation and expressions
- Sandbox mode for testing (simulates external actions)

### Flow Compiler (`core/compiler.py`)
- Validates flow graph structure
- Compiles nodes to executable format
- Resolves node dependencies and connections

### Node Executors (`core/executors/`)
- `base.py`: Base executor interface
- `crm.py`: CRM operations (contact, ticket, deal CRUD)
- `messaging.py`: WhatsApp, email sending
- `http.py`: HTTP request nodes
- `triggers.py`: Trigger node handling
- `debug.py`: Debug/logging nodes

### Schedule Service (`core/schedule_service.py`)
- Celery Beat integration
- Schedule CRUD operations
- Dynamic schedule registration

### Signal System (`core/signals.py`)
- Event trigger matching
- Flow dispatch on events

## Execution Modes

### Production Mode
- Executes published versions
- External actions performed
- Full execution logging

### Testing Mode (Sandbox)
- Executes testing versions
- External actions simulated
- Results streamed via WebSocket

### Preview Mode
- Executes draft versions
- All actions simulated
- Live node-by-node feedback

## Data Lab node catalog

Flows can orchestrate Data Lab via dedicated nodes (all tenant-scoped):

| Node | Purpose | Outputs |
|------|---------|---------|
| `datalab_ingest` | Create a FileAsset from `file_id` (pass-through), `url`, or `content_base64` | `file_id`, `filename`, `content_type`, `size`, `storage_key` |
| `datalab_file_adapter` | Run an ImportProcess on a file/fileset | `resultset_id`, `row_count`, `schema` |
| `datalab_resultset_get` | Fetch ResultSet metadata and optional preview (bypasses API fencing) | `resultset_id`, `schema_json`, `row_count`, `preview_json`, `origin`, etc. |
| `datalab_promote` | Promote a ResultSet to a Dataset (new or new version) | `dataset_id`, `version_number`, `row_count` |

**Recommended pattern:** Ingest file → Data Lab Import → Get ResultSet (for scripts) → Flow Script (decisions/normalization) → Promote to Dataset for analytics.

Flow Scripts can receive ResultSet data by using `input_payload` with `$datalab_resultset` references (resolved before the run) or by wiring the output of `datalab_resultset_get` into the script node.

## What it Does NOT Do

- Does not manage contacts (uses crm)
- Does not send messages directly (uses chatbot messenger)
- Does not handle authentication (delegates to portal)
- Does not store data permanently (uses datalab for data processing)
