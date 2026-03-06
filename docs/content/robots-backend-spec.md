# Robots Backend Spec (Robot Studio External Frontend)

This document defines the backend contract for Robot Studio when the frontend is hosted in a separate repository.

## 1) Scope

- Backend-only implementation in `moio_platform`.
- Frontend (Robot Studio) consumes REST + WebSocket APIs from this backend.
- Durable control state is `intent_state` (RobotPlan), separate from transcript.

## 2) Data Model

## `Robot`

- Identity/configuration for a robot.
- Key fields:
  - `name`, `slug`, `description`
  - `system_prompt`, `bootstrap_context`
  - `model_config`, `tools_config`
  - `targets`, `operation_window`, `schedule`
  - `compaction_config`, `rate_limits`
  - `enabled`, `hard_timeout_seconds`

## `RobotSession`

- Durable conversation/workflow context.
- Key fields:
  - `session_key` (required prefixes: `manual:`, `schedule:`, `event:`, `campaign:`)
  - `metadata`
  - `transcript` (JSON blob, V1)
  - `intent_state` (RobotPlan)
  - `run_id` (current/last run pointer)

## `RobotRun`

- Execution unit.
- Key fields:
  - `status`: `pending|running|success|failed|cancelled`
  - `trigger_source`, `trigger_payload`
  - `usage` (`iterations`, `llm_calls`, `tool_calls`, `tokens`, `compactions_performed`)
  - `execution_context`, `output_data`, `error_data`
  - `cancel_requested_at`

## `RobotMemory`

- Optional long-lived facts/summaries.
- Key fields: `kind`, `payload`, `expires_at`, `session`.

## `RobotEvent` (mandatory)

- Immutable event stream and audit log for robot lifecycle, assistant, tools and metrics.
- Used by:
  - timeline rendering in Studio
  - debugging/replay
  - run/session observability

## 3) Execution Loop Contract

Task: `robots.tasks.execute_robot_run(run_id)`

Loop behavior:

1. Lock `RobotRun` and set `running`.
2. Ensure `RobotSession`.
3. Guards:
   - cancellation
   - `operation_window`
   - daily limits (`max_daily_runs`, tokens/tool calls/messages)
4. Compaction checks:
   - proactive compaction when token estimate exceeds threshold
   - hard cap enforcement by transcript entry count
5. LLM output contract validation.
6. Tool-call handling (stub-ready, sanitized/truncated outputs).
7. Apply `plan_patch` to `intent_state` with invariants.
8. Persist transcript + usage + output.
9. Emit `RobotEvent` and WebSocket push.

## 4) Input Contracts

## Trigger payload (`instruction_payload`)

- Allowed keys:
  - `instruction_schema_version` (int, default `1`)
  - `instruction` (string)
  - `objective_override` (object)
  - `queue_items` (array)
  - `constraints` (object)
  - `metadata` (object)
  - `session_key` (string, optional)
  - `trigger_source` (string, optional)

Unknown keys are rejected with HTTP 400.

## LLM output contract

Required keys:

- `assistant_message` (string)
- `tool_calls` (array)
- `plan_patch` (object or null)
- `stop_reason` (string)

## 5) RobotPlan (`intent_state`) invariants

Server validates every patch:

- `queue.cursor` is monotonic.
- `current.item_id` belongs to `queue.items` when present.
- `current.attempt` max cap (<= 5).
- Budgets (`daily_*_remaining`) cannot increase during a run.
- `blocked_until` cannot exceed max delay window.

## 6) REST API

Base: `/api/v1/robots/`

OpenAPI:

- Endpoints are annotated with `drf-spectacular`.
- Schema is available at `/api/schema/`.
- Suggested external frontend flow:
  1. pull schema from `/api/schema/`
  2. generate typed client
  3. pin generated client to backend release tag

## Robots

- `GET /` list robots
- `POST /` create robot
- `GET /{robot_id}/` retrieve
- `PATCH /{robot_id}/` partial update
- `POST /{robot_id}/trigger/` enqueue run
- `GET /{robot_id}/runs/` list runs for robot
- `GET /{robot_id}/events/` list events for robot
- `GET /{robot_id}/sessions/` list sessions for robot
- `GET|POST /{robot_id}/memories/` list/create memory entries
- `POST /{robot_id}/runs/{run_id}/cancel/` request cancel

## Global

- `GET /contracts/` backend-declared input/output contracts
- `GET /runs/` list runs across tenant
- `GET /runs/{run_id}/` run detail
- `POST /runs/{run_id}/cancel/` cancel run
- `GET /runs/{run_id}/events/` run timeline events
- `GET /sessions/` list sessions across tenant
- `GET /sessions/{session_id}/` session detail (+ transcript)
- `PATCH /sessions/{session_id}/intent-state/` admin/manual intent patch

## 7) WebSocket API

Endpoint:

- `ws/robots/{robot_id}/runs/stream/`

Auth:

- JWT Bearer token in query/header (same pattern as existing WS consumers).

Flow:

- Connect to robot-level stream.
- Client sends:
  - `{ "action": "start_stream", "data": { "run_id": "<uuid>" } }`
- Client receives run-level events.

Event categories pushed:

- `lifecycle.started|completed|failed|cancelled`
- `assistant.message`
- `tool.started|tool.completed`
- `metrics`

## 8) Guards and Safety

Pre-enqueue guards:

- `operation_window`
- `max_daily_runs`

In-loop guards:

- `max_daily_tokens`
- `max_daily_tool_calls`
- `max_daily_messages_sent`
- cancellation checks each iteration

Data handling:

- Tool outputs are sanitized and truncated (100 KB cap in current implementation).

## 9) Scheduling

Service: `robots.schedule_service.RobotScheduleService`

Supported schedule formats in `Robot.schedule`:

- `{ "kind": "cron", "expr": "0 9 * * 1-5", "tz": "Europe/Madrid" }`
- `{ "kind": "interval", "seconds": 3600 }`
- `{ "kind": "one_off", "run_at": "<datetime>" }`

Task executed by beat:

- `robots.tasks.execute_scheduled_robot(robot_id)`

## 10) Frontend Integration Checklist (External Repo)

- Use `/contracts/` to validate client payload builders.
- Use REST for CRUD and historical fetches.
- Use WS for live run timeline.
- Render plan panel from run/session `intent_state`.
- Render usage panel from `run.usage`.
- Implement optimistic cancel and refresh run detail.

## 11) Known V1 Limits

- LLM/tool execution is scaffold-first in backend loop; tool execution adapters should be expanded per domain tool registry.
- Transcript storage is JSON blob (migration path to entry-table remains planned).

## 12) Migration Readiness (V2)

Recommended trigger points for moving to `RobotTranscriptEntry`:

- sustained > 1,500-2,000 transcript entries/session
- high read/write contention on session row
- analytics/replay requiring entry-level indexing

Planned migration approach:

1. dual-write (blob + entry rows)
2. backfill historical blobs
3. switch read path
4. retire blob or keep compact summary
