---
title: "Flows Data Model"
slug: "flows-data"
category: "flows"
order: 4
status: "published"
summary: "- id: UUID (PK) - name: CharField - description: TextField - status: CharField (active, inactive, error) - published_version: FK → FlowVersion - execution_count: PositiveIntegerField - last_executed_a"
tags: ["flows"]
---

## Overview

- id: UUID (PK) - name: CharField - description: TextField - status: CharField (active, inactive, error) - published_version: FK → FlowVersion - execution_count: PositiveIntegerField - last_executed_a

# flows - Data

## Owned Data Models

### Flow

- id: UUID (PK)
- name: CharField
- description: TextField
- status: CharField (active, inactive, error)
- published_version: FK → FlowVersion
- execution_count: PositiveIntegerField
- last_executed_at: DateTimeField
- last_execution_status: CharField
- created_by: FK → User
- tenant: FK → Tenant

Constraint: unique (tenant, name)

### FlowVersion

- id: UUID (PK)
- flow: FK → Flow
- version: PositiveIntegerField (auto-increment per flow)
- status: CharField (draft, testing, published, archived)
- label: CharField
- notes: TextField
- graph: JSONField
- config_schema: JSONField
- config_values: JSONField
- published_at: DateTimeField
- testing_started_at: DateTimeField
- created_by: FK → User
- tenant: FK → Tenant

Constraints:
- unique (flow, version)
- one_testing_per_flow
- one_published_per_flow

FSM Transitions:
- draft → testing (start_testing)
- testing → draft (back_to_design)
- draft/testing → published (publish)
- published → archived (archive)

### FlowExecution

- id: UUID (PK)
- flow: FK → Flow
- status: CharField
- started_at, completed_at: DateTimeField
- duration_ms: PositiveIntegerField
- input_data, output_data, error_data: JSONField
- trigger_source: CharField
- execution_context: JSONField

### FlowInput

- id: UUID (PK)
- flow: FK → Flow
- name: CharField
- description: TextField
- data_type: CharField
- is_required: BooleanField
- default_value: JSONField
- created_by: FK → User

### FlowSchedule

- id: UUID (PK)
- flow: OneToOne → Flow
- schedule_type: CharField (cron, interval, one_off)
- cron_expression: CharField
- interval_seconds: PositiveIntegerField
- run_at: DateTimeField
- timezone: CharField
- is_active: BooleanField
- next_run_at, last_run_at: DateTimeField
- celery_task_name: CharField
- tenant: FK → Tenant

### FlowSignalTrigger

- id: UUID (PK)
- flow: FK → Flow
- model_path: CharField (e.g., 'crm.Contact')
- signal_type: CharField
- only_on_create, only_on_update: BooleanField
- watch_fields: JSONField
- field_conditions: JSONField
- is_active: BooleanField
- name, description: CharField/TextField
- execution_count: PositiveIntegerField
- last_triggered_at: DateTimeField
- tenant: FK → Tenant

### FlowWebhook

- id: UUID (PK)
- flow: OneToOne → Flow
- endpoint_path: CharField
- http_method: CharField
- secret_token: CharField
- allowed_ips: JSONField
- headers_validation, payload_validation: JSONField
- total_calls: PositiveIntegerField
- last_called_at: DateTimeField

### FlowGraphVersion (LEGACY)

- id: UUID (PK)
- flow: FK → Flow
- major, minor: IntegerField
- is_published: BooleanField
- graph: JSONField
- notes: TextField
- preview_armed: BooleanField
- preview_armed_at: DateTimeField
- preview_armed_by: FK → User

### FlowScript

- id: UUID (PK)
- flow: FK → Flow
- name, slug: CharField/SlugField
- description: TextField
- tenant: FK → Tenant

### FlowScriptVersion

- id: UUID (PK)
- script: FK → FlowScript
- flow: FK → Flow
- version_number: PositiveIntegerField
- code: TextField
- requirements: TextField
- parameters: JSONField
- notes: TextField
- published_at: DateTimeField
- tenant: FK → Tenant

### FlowScriptRun

- id: UUID (PK)
- script: FK → FlowScript
- version: FK → FlowScriptVersion
- flow: FK → Flow
- status: CharField
- input_payload, output_payload, error_payload: JSONField
- celery_task_id: CharField
- started_at, completed_at: DateTimeField
- tenant: FK → Tenant

### FlowScriptLog

- id: UUID (PK)
- run: FK → FlowScriptRun
- level: CharField (info, warning, error)
- message: TextField
- details: JSONField
- tenant: FK → Tenant

### EventDefinition

- id: UUID (PK)
- name: CharField (unique, e.g., 'deal.won')
- label: CharField
- description: TextField
- entity_type: CharField
- payload_schema: JSONField
- hints: JSONField
- active: BooleanField
- category: CharField

### EventLog

- id: UUID (PK)
- name: CharField
- tenant_id: UUIDField
- actor, entity: JSONField
- payload: JSONField
- occurred_at, created_at: DateTimeField
- correlation_id: UUIDField
- source: CharField
- routed: BooleanField
- routed_at: DateTimeField
- flow_executions: JSONField

### ScheduledTask

- id: UUID (PK)
- name, description: CharField/TextField
- task_name: CharField (Celery task)
- task_args, task_kwargs: JSONField
- schedule_type: CharField
- cron_expression: CharField
- interval_seconds: PositiveIntegerField
- run_at: DateTimeField
- timezone: CharField
- status: CharField (active, paused, completed, failed)
- is_active: BooleanField
- celery_task_name: CharField
- next_run_at, last_run_at: DateTimeField
- run_count, error_count: PositiveIntegerField
- created_by: FK → User
- tenant: FK → Tenant

### TaskExecution

- id: UUID (PK)
- scheduled_task: FK → ScheduledTask
- status: CharField
- started_at, finished_at: DateTimeField
- duration_ms: PositiveIntegerField
- celery_task_id: CharField
- input_data, result_data: JSONField
- error_message, error_traceback: TextField
- trigger_type: CharField
- tenant: FK → Tenant

### FlowAgentContext

- id: UUID (PK)
- flow_execution: OneToOne → FlowExecution
- shared_variables: JSONField
- conversation_history: JSONField
- tool_calls_log: JSONField
- reasoning_trace: TextField
- status: CharField (active, completed, failed)
- started_at, completed_at: DateTimeField
- metadata: JSONField
- tenant: FK → Tenant

### FlowAgentTurn

- id: UUID (PK)
- context: FK → FlowAgentContext
- run_index: PositiveIntegerField
- agent_name: CharField
- node_id: CharField
- input_payload, output_payload: JSONField
- tool_calls, messages, errors: JSONField
- status: CharField
- started_at, completed_at: DateTimeField
- duration_ms: PositiveIntegerField

## External Data Read

- portal.Tenant
- portal.MoioUser

## External Data Written

- Updates Flow.published_version on publish
