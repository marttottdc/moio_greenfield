# Flows Composer Assessment and Plan

## 1. Current State Overview

### 1.1 Data model
- `Flow` captures the business metadata (trigger type, handler type, status, configs) and is already related to tenants and creators. It stores trigger/handler configuration blobs but does **not** yet keep a normalized graph structure. [flows/models.py]
- `FlowGraphVersion` stores JSON snapshots of the canvas graph (`nodes`, `edges`, `meta`) for each flow version and is used to create drafts and published versions. The combination of `(flow, major, minor)` is unique and the latest entry drives the builder view. [flows/models.py]
- `FlowExecution` logs preview/real runs but is currently only used by the preview endpoint to record lightweight telemetry. [flows/models.py]

### 1.2 Views and endpoints
- The list, create, builder, import/export, publish, toggle, and preview endpoints are present. Creation immediately seeds a default graph with trigger/output nodes and redirects to the builder. [flows/views.py]
- `flow_builder` persists drafts by POSTing the full graph JSON to create a new `FlowGraphVersion` (minor+1). Preview executes the current graph in-memory with `preview_execute`. There is no granular API (nodes/edges CRUD) yet. [flows/views.py]

### 1.3 Front-end builder
- The React-based builder is the canonical UI (`flow_builder_react.html`). It bootstraps a Vite-built bundle from `flows/static/flowbuilder-react/` and consumes backend endpoints for flow detail/save/validate/publish/preview. [flows/templates/flows/flow_builder_react.html]
- Node kinds and their metadata are provided by the backend registry serializer (`node_definitions`) and exposed via the flow detail payload (and related APIs). [flows/views.py, flows/core/registry.py]

### 1.4 Runtime and registry
- `flows/core/registry.py` defines a decorator-based runtime registry but only includes basic trigger/output executors. Logic/transform nodes are absent. The registry only returns callables; there is no metadata for the builder (labels, config schema, port definitions). [flows/core/registry.py]
- `preview_execute` performs a depth-first traversal executing registered executors. It expects `graph['nodes']` to include IDs and `kind` values that match registry entries. There is no validation or context pipeline yet. [flows/core/runtime.py]
- `connector.FlowConnector` is a separate mechanism that maps `Flow` definitions to triggers/handlers, but it is not connected to the builder graph yet. [flows/core/connector.py]

## 2. Gaps Blocking a Working Composer
1. **Graph schema contract** – Nodes/edges structure is implied but not validated. Builders and runtime could diverge without a shared schema (e.g., ports, config types) and edges cannot surface the real data moving through each connection.
2. **Node registry metadata** – The runtime registry lacks descriptive metadata for palette display and for generating configuration UIs. Nodes can execute but cannot self-describe.
3. **Backend access for composer UI** – Palette and node editors are hardcoded on the client; there is no API to fetch available node kinds or to resolve registry-backed objects (tasks, agents, etc.).
4. **Persisted flow activation** – Saving drafts creates `FlowGraphVersion` rows but does not synchronize `Flow` trigger/handler configs or publish to `FlowConnector`. Publishing merely snapshots the same graph JSON.
5. **Execution pipeline** – Preview execution is synchronous and serial; there is no orchestration bridge to Celery/tasks when a flow is activated.
6. **Testing coverage** – Only smoke tests exist; there are no tests for registry resolution, preview execution, or builder persistence API.

## 3. Plan to Achieve a Working Composer

### Phase 1 – Formalize graph contracts
1. Define a typed schema (e.g., Pydantic dataclasses or JSON Schema) in `flows/core/schema.py` for nodes, edges, and the overall graph. Include port definitions, config dict validation, metadata fields, and a way to express the input/output data schema available at each port so edges can mirror the actual data flow.
2. Add validation hooks in `flow_builder` POST handler and `preview_execute` to ensure graphs conform before saving/executing.
3. Create serializers to convert between schema objects and the stored JSON snapshots.

### Phase 2 – Expand the node registry
1. Extend `flows/core/registry.py` to support registering a `NodeDefinition` object that includes: execution callable, display label/category, default config, config schema, port definitions, and references to backend objects (Celery task path, agent identifier, webhook slug, etc.).
2. Build registry loading helpers that can resolve dotted paths via Django import strings and optionally query domain-specific sources (e.g., CRM entities, agents, campaigns). Cache resolution to avoid repeated imports.
3. Document registry conventions (naming, expected payload contracts) and seed built-in node definitions for triggers, logic, transforms, outputs, and integrations, including how each node extends or constrains the data schemas on its input/output ports so downstream edges expose the right payload preview.

### Phase 3 – Backend APIs for the composer
1. Expose a read-only endpoint (`/flows/api/nodes/`) that returns the registry catalog for use by the palette (grouped categories, icons, config schema, default values) together with declarative port schemas that let the builder highlight what data an edge will emit or receive.
2. Provide endpoints to resolve dynamic options (e.g., listing available agents/tools) referenced from node config UIs.
3. Update the builder JS to fetch palette/metadata from the API rather than hardcoding definitions. Generate config forms dynamically from the schema.

### Phase 4 – Persistence and publication workflow
1. Introduce a `FlowGraphVersion` flag for "latest draft" and ensure only one active draft per flow (overwrite instead of creating unbounded minors or prune old minors).
2. On publish, materialize the graph into executable structures: extract trigger settings, register nodes with `FlowConnector`, and persist resolved handler configurations back onto the `Flow` record.
3. Implement synchronization logic so that enabling/disabling a flow registers/unregisters it with runtime connectors.

### Phase 5 – Execution bridge
1. Enhance `preview_execute` to leverage the new registry metadata (port routing, context passing, and port-level data schemas) and to catch/report node-level errors with meaningful diagnostics.
2. Design a runtime adapter that, when flows are published, compiles the graph into an execution plan (e.g., Celery chain or async job) with support for registry-based nodes.
3. Store execution artifacts (timeline, outputs) in `FlowExecution` and expose them in the UI for debugging.

### Phase 6 – QA and documentation
1. Add unit tests for registry registration/resolution, graph validation, save/publish flows, and preview execution with sample graphs.
2. Document developer workflow: how to add new node kinds, how to test flows locally, and API contracts for composer UI.
3. Provide user-facing documentation and onboarding for the composer once the workflow is stabilized.

## 4. Deliverables Checklist
- [ ] Graph schema definitions and validation in backend.
- [ ] Node registry with metadata + APIs for palette/config.
- [ ] Builder UI consuming registry API (dynamic palette and editors) with edge inspectors that surface live input/output schemas based on the data flow.
- [ ] Publication pipeline writing runtime-ready flow definitions and syncing with `FlowConnector`.
- [ ] Enhanced preview/runtime execution path with instrumentation.
- [ ] Automated tests and docs covering composer lifecycle.

## 5. Open Questions / Decisions Needed
- How should branching/parallelism be represented (single out port per rule vs. dynamic port naming)?
- Should we leverage existing workflow engines (e.g., Prefect, Temporal) or continue with custom runtime?
- What security constraints exist around loading tasks/agents from the registry (multi-tenant isolation, permission checks)?
- How will long-running or async agents report back into the flow execution timeline?

Answering these questions early will de-risk later phases, especially around registry governance and runtime scalability.
