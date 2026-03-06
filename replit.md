# Moio Platform - Django Multi-Tenant Application

## Overview
Moio Platform is a Django-based multi-tenant application designed to centralize business operations. It offers CRM, chatbot, recruitment, calendar, and asset management functionalities. The platform supports multiple tenants with isolated data and customizable configurations, enhancing customer interaction through AI, streamlining recruitment, and efficiently managing assets. A key feature is its advanced AI capabilities, including a visual flow builder for orchestrating AI agents, making it a powerful tool for automating and optimizing business workflows.

## User Preferences
I prefer to receive clear and concise instructions. When making changes, please ensure that:

### Development Focus
- **API-only development**: All new development is for REST API endpoints in `api/v1/`. No internal frontend development.
- **Frontend code is reference-only**: Existing templates/HTMX code can be used as reference but not extended or modified.
- **No legacy accommodation without asking**: Never adapt code to make both old and new approaches work without explicit approval. Legacy is small.
- **No stubs or sweeping issues under the rug**: If something doesn't work, fix it properly or ask. Don't create placeholder implementations.

### Code Standards
- Development follows Django best practices, PEP 8, and uses type hints.
- All tenant-specific models inherit from `TenantScopedModel`.

### Legacy Reference (not actively developed)
- HTMX 2.0.6-first approach for dynamic interactions (reference only)
- CSS centralized in `portal/static/css/crm.css` (reference only)
- Views differentiate between HTMX and regular requests (reference only)
- Modals in `/appname/templates/modals/` (reference only)

## System Architecture

### Core Applications
The platform is structured around several core Django applications:
- **portal**: User authentication, tenant management, core configurations.
- **crm**: Customer relationships, contacts, orders, products, ticketing, deals/opportunities.
- **chatbot**: AI-powered chatbot with WhatsApp integration.
- **recruiter**: Recruitment processes, candidates, job postings.
- **moio_calendar**: Calendar and scheduling capabilities.
- **fam**: Fixed Asset Management system.
- **flows**: AI Agent Orchestration and visual workflow management.

### Key Features and Design
- **Multi-tenancy**: Implemented via `TenantScopedModel` for data isolation.
- **AI Agent Orchestration (Flows App)**: Visual drag-and-drop builder for AI agents supporting multi-trigger events (webhooks, signals, scheduled tasks) and integrating with OpenAI Agent SDK. Includes platform tools and logic nodes.
- **Knowledge Repository**: `KnowledgeItem` model for structured data retrieval by AI agents, featuring REST API with CRUD, various content types, and tenant isolation.
- **Asynchronous Processing**: Celery for background and periodic tasks.
- **Real-time Features**: WebSockets for notifications via Django Channels with tenant-aware consumers for tickets, WhatsApp, and campaigns.
- **Caching**: Redis for caching and session storage.
- **API Development**: Django REST Framework for API endpoints with authentication and permissions, including comprehensive CRUD operations for CRM entities (contacts, tickets, deals, etc.) and standardized pagination.
- **UI/UX**: HTMX 2.0.6-first approach, centralized CSS, standardized template structure with partials for HTMX, and consistent modal design.
- **Integration System**: Extensible, plugin-style integration configuration supporting multi-instance per tenant.
- **Authentication**: REST APIs use `CsrfExemptSessionAuthentication` with `TenantJWTAAuthentication`.
- **Campaign Flow V2**: FSM-based workflow for campaign creation (WhatsApp, Email, SMS, Telegram) with step-gated transitions and SSE streaming for live monitoring.
- **Deals/Opportunities API**: Comprehensive system for managing sales pipelines, stages, and deals, including comments and tenant-scoped security.
- **Event-Driven Flow Triggers**: Flows can be triggered by domain events (e.g., `deal.created`, `deal.stage_changed`, `ticket.created`, `ticket.updated`, `ticket.closed`) using the event system. Events are emitted via `emit_event()` API, persisted in `EventLog` for audit/replay, and routed to matching flows asynchronously. The `EventDefinition` model catalogs available events with schemas. Signal-based triggers have been fully deprecated in favor of this deterministic event-based approach.
- **Flow State Model**: Flows follow a Draft → Testing → Published → Archived lifecycle with preview support:
  - **Draft**: Editable and previewable. Multiple parallel drafts are supported.
  - **Testing**: Preview mode that receives configured trigger events in sandbox isolation. Can transition to Draft or Published.
  - **Published**: Locked for editing, receives production events in non-sandbox mode.
  - **Archived**: Used for logs/history (rollback candidate).
  - "New Version" clones the active published version into a new draft.
- **Testing Version Execution**: Both published and testing versions receive webhook and event-triggered executions:
  - `execute_flow_webhook` dispatches **both** versions **asynchronously** via Celery for immediate parallel execution
  - Published version runs in production mode (`sandbox=False`)
  - Testing version runs in sandbox mode (`sandbox=True`)
  - Webhook returns immediately with dispatch confirmation, not blocking on execution
  - `execute_flow` Celery task accepts `version_id` and `sandbox` parameters for explicit control
  - Draft versions are **never** executed via webhooks/events
  - Testing versions set `sandbox=True` in execution context and `$sandbox` context variable
  - `flow_connector_handler` (formerly `execute_published_flow`) is the glue between FlowConnector nodes and execution engine
- **Testing Mode (Armed/Disarmed)**: Testing versions respond to real trigger events in sandbox mode:
  - **Armed** = Flow version status `testing` → responds to real webhooks/events in sandbox mode
  - **Disarmed** = Flow version status `draft` → does not respond to triggers
  - No waiting executions created - flows execute immediately when triggers fire
  - Simple state model: arm to test with real data, disarm when done
- **Sandbox Execution**: Testing versions execute in complete sandbox isolation with no external side effects:
  - All external API calls (WhatsApp, email, HTTP, CRM operations) return simulated responses
  - Sandbox results include `success=True, sandbox=True, sandbox_action=<action>` with realistic fake IDs/metadata
  - Execution steps stream in real-time via WebSocket with `execution_mode="preview"` flag
  - The `$sandbox` context variable propagates through all tool executors in `flows/core/registry.py`
  - Simulated responses are formatted for frontend display while clearly marked as sandbox operations
- **Flow Executors Package**: Synchronous executor functions for flow nodes (messaging, CRM, HTTP, triggers, outputs) with unified `ExecutorResult` pattern. Executors run within the parent flow execution Celery task, not as separate tasks.
  - `send_whatsapp_template`: Synchronous executor for WhatsApp template sending with support for both `values` (preferred) and `parameters` (backwards compatibility) parameter names.
  - `send_email_template`: Synchronous executor for email template sending.
- **Trigger Output Format**: All trigger nodes (webhook, event, manual, scheduled, process) return the raw payload directly without wrapping. Expressions like `{{input.field}}` resolve correctly to the trigger payload fields.
- **Expression Evaluation**: Expressions in branch rules, conditions, loops, and templates support dot notation for intuitive dictionary access (e.g., `input.template_id`, `ctx.Webhook.data`, `payload.nested.field`) via `DotAccessDict` wrapper class in `flows/core/lib.py`.
- **Node Definitions Icons**: All node types use Lucide icon library with semantic icons (e.g., Split for Branch, Repeat for While, Zap for Event, BrainCircuit for AI Agent).
- **Set Values Node** (`data_set_values`): Data node that injects fixed key-value pairs into the flow. Supports:
  - Any number of key-value pairs via `values` array: `[{key: "name", value: "John"}, ...]`
  - Optional `merge_with_input` to combine with incoming payload
  - Expression support in values using `{{payload.field}}` syntax
  - Category: "Data", Icon: "FileInput"
- **Formula Node** (`data_formula`): Transform data using formulas with functions:
  - String: `concat()`, `upper()`, `lower()`, `trim()`, `replace()`, `substring()`, `length()`, `split()`
  - Numeric: `round()`, `floor()`, `ceil()`, `abs()`, `min()`, `max()`, `sum()`
  - DateTime: `now()`, `today()`, `date_add()`, `date_diff()`, `format_date()`, `parse_date()`
  - Logic: `if_else()`, `coalesce()`, `is_null()`, `is_empty()`
  - Access upstream values with `payload.field` syntax
  - Category: "Data", Icon: "Calculator"

- **WebSocket Infrastructure**: Centralized real-time event streaming with JWT authentication and tenant isolation, providing updates for tickets, WhatsApp messages, campaign statistics, and **flow execution monitoring**. All flow executions (preview, sandbox, and production) emit live events: `execution_started`, `node_started`, `node_finished`, `node_error`, `execution_completed`.
- **Execution Mode Tagging**: All WebSocket events and execution records include `execution_mode` field:
  - `"production"` - Published version running in production mode (sandbox=False)
  - `"testing"` - Testing version running in sandbox mode (sandbox=True)  
  - `"preview"` - Manual preview execution via the preview API
- **Flow Execution Logs API**: Comprehensive endpoints for querying execution history:
  - `GET /api/flows/{flow_id}/executions/` - List executions for a specific flow with filtering
  - `GET /api/flows/{flow_id}/executions/{execution_id}/` - Get detailed execution data with full timeline
  - `GET /api/flows/executions/` - List all executions across all flows (tenant-scoped, staff can see all)
  - `GET /api/flows/executions/running/` - List currently running/pending executions for real-time monitoring
  - Filters: `status`, `trigger_source`, `execution_mode`, `flow_id`, `limit`, `offset`
- **Execution Serialization**: Each execution record includes: `execution_mode`, `trigger_source`, `sandbox`, `flow_id`, `flow_name`, `graph_version`, `timeline`, `input`, `output`, `error`, `duration_ms`, and timestamps.

## API Documentation
- See `docs/flows_api_reference.md` for comprehensive Flows API documentation for frontend integration.
- See `docs/FLUIDCMS_FRONTEND_ACTION_HANDLERS.md` for FluidCMS CTA action system frontend implementation guide.

### FluidCMS CTA Action System
CTA buttons and links in FluidCMS blocks support 10 action types:
- `none`, `external_link`, `internal_link`, `scroll_to_anchor`
- `topic_chat`, `article_chat` (opens chat modal with WebSocket to `/ws/crm-agent/`)
- `simple_modal`, `legal_document`, `reveal_content`, `collapse_content`

Blocks can include `hidden` content with `conversation_initiator` and `agent_instructions` for chat context injection. Legacy `href` format remains supported for backward compatibility.

## External Dependencies
- **OpenAI API**: AI-powered chatbot, chat completions, embeddings, and function calling.
- **WhatsApp Business API**: Chatbot integration, message templates, automated responses.
- **AWS S3**: File storage and static asset management.
- **PostgreSQL**: Primary database.
- **Redis**: Caching, session management, Celery message broker.
- **Google Maps API**: Location-based services.
- **Mercado Pago**: Payment gateway integration.
- **WooCommerce**: E-commerce platform integration.
- **Other Recruitment Platforms**: Various integrations for recruitment functionalities.