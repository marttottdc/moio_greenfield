# Sprint: Plugins as Platform-Managed Capability Bundles

## Goal

Define plugins as platform-managed capability bundles that can be installed, validated, approved, configured, and selectively exposed to tenant users.

The runtime must only include a plugin in the active agent configuration when all of that plugin's requirements are satisfied.

## Why This Sprint Exists

We want a structured extension system that supports:

- powerful integrations
- large API surfaces with low token overhead
- tenant-level and user-level auth requirements
- strong admin governance
- explicit activation rules

This should not rely on arbitrary unstructured Python snippets being silently available to all agents.

## Product Direction

A plugin is broader than "code that registers a few tools."

A plugin is a capability bundle that may include:

- manifest metadata
- Python runtime code
- schema assets (for example OpenAPI)
- searchable resource indexes
- auth requirements
- config schema
- admin UI metadata for setup and validation

## Core Design Decisions

1. Install is not activation

A plugin may be installed and visible to admins without being active for any agent.

2. Platform admin controls platform availability

Platform admins approve or install plugin bundles and decide whether they are available to tenants at all.

3. Tenant admins control tenant enablement and user assignment

Tenant admins decide whether an approved plugin is enabled for their tenant and which users or roles may use it.

4. Requirements must be satisfied before runtime exposure

If a plugin cannot be fully instantiated for the current tenant/user/profile context, it must not appear in the agent's tool or resource catalog.

5. Runtime inclusion is readiness-based

Readiness is not a UI-only concept. It is a runtime gate enforced before tools are assembled.

## Hard Invariant

If a plugin cannot instantiate successfully, it cannot be added to the agent tools.

Known-but-inactive is valid.

Partially loaded in the tool catalog is not valid.

## Target Lifecycle

The intended lifecycle is:

- installed
- validated
- platform-approved
- tenant-enabled
- requirements satisfied
- active for agent

Any failure in requirements or initialization keeps the plugin out of the active agent configuration.

## Requirement Types

Typical plugin requirements may include:

- required tenant config present
- required user config present
- required tenant credential present
- required user credential present
- schema assets available and indexed
- manifest-valid permissions approved
- initialization/health check passes

## Runtime Resolution Order

Given tenant + user + optional workspace + selected profile:

1. Start from platform-approved plugins.
2. Filter to tenant-enabled plugins.
3. Filter to plugins allowed for the user's role or assignment.
4. Resolve plugin config and credentials at tenant and user scope.
5. Validate requirements and instantiate.
6. Expose only the plugins that instantiated successfully.

Everything else remains installed metadata, not active runtime surface.

## Preferred Plugin Shape

Plugins should be treated as platform-managed bundles, not ad hoc code folders.

Good bundle inputs:

- a structured plugin form that collects required assets and config
- a validated zip upload that is checked before installation

Validation should happen before code import or activation. The platform should reject malformed or incomplete packages early.

## API-Focused Plugin Direction

One of the highest-value plugin types is a large API integration bundle.

For large APIs, the right model is not hundreds of handwritten tools. The better model is:

- searchable schema/resource index
- narrow metadata lookup for specific operations
- constrained operation execution

This keeps token use low because the agent retrieves only the relevant operation details on demand.

## Preferred Runtime Surface For Schema-Heavy Plugins

Schema-heavy plugins should lean toward a small set of primitives such as:

- search resources / operations
- describe one operation or resource
- call one approved operation

That is more scalable and more auditable than exposing the full schema in prompts.

## Intended Domain Model

The exact schema can evolve, but the architecture should converge toward:

- `Plugin`
- `PluginVersion`
- `TenantPluginEnablement`
- `UserPluginAssignment` (or role-based equivalent)
- `PluginCredentialBinding`

Plugin readiness should be derived from these records plus bundle metadata, not from guesswork at runtime.

## Auth Model Guidance

Plugins may require credentials at different scopes:

- tenant-level service credentials
- user-level credentials

The plugin should declare what it needs, and the platform should resolve those requirements through a common credential framework rather than a bespoke auth flow per plugin.

## Out of Scope For This Sprint

- full arbitrary background service support
- unrestricted direct database access from plugins
- plugin sandboxing as a first-class security boundary
- turning every internal subsystem into a plugin immediately

The focus is the lifecycle, gating, and runtime resolution contract.

## Open Questions

- Do we want role-based assignment, explicit user assignment, or both in v1?
- What should be the minimum readiness check for activation: config only, or config plus live health validation?
- Should plugin bundles be stored on disk only, or do we also persist bundle metadata in the database?
- Which plugin types are allowed in v1: resource/API plugins only, or also tool/hook/skill bundles?
- How much of plugin setup should be driven by manifest-declared UI forms?

## Implementation Checklist

- Define the plugin bundle contract: manifest fields, required assets, versioning, and permission declarations.
- Implement bundle validation that runs before import or activation, including zip structure and asset checks.
- Define persistent records for install state, approval state, tenant enablement, assignment, and credential bindings.
- First implementation cut: sync validated disk bundles into platform plugin records, then resolve platform approval and tenant enablement from DB before runtime readiness gating.
- Next implementation cut: expose admin APIs so platform approval and tenant enablement can be managed without manual database edits.
- Implement readiness evaluation so a plugin is excluded unless all required config, credentials, assets, and checks pass.
- Build the runtime resolution pipeline from platform-approved to tenant-enabled to user-allowed to instantiated.
- Start with an API/resource plugin MVP that supports search, describe, and constrained execution over indexed schema assets.
- Keep runtime integration narrow: only fully active plugins contribute tools or resources to the agent catalog.
- Reuse a common tenant/user credential framework instead of plugin-specific auth logic.
- Add operator diagnostics so admins can see exactly why a plugin is inactive.
- Add tests for readiness gating, credential scope resolution, and failure behavior during runtime assembly.

## Suggested Branch

`codex/plugins`

## Progress Update (March 4, 2026)

Completed in this sprint branch:

- Added tenant plugin assignment records (`role` and `user`) in the public schema.
- Extended tenant plugin admin APIs to manage assignments together with tenant enablement/config.
- Extended plugin registry state payloads with assignment data for platform and tenant admin views.
- Added runtime user-assignment gating so plugin aliases are excluded from tool catalogs/execution when the initiator is not allowed.
- Added user-assignment aware `pluginsStatus` reporting (`user_assignment` stage when blocked).
- Added plugin entrypoint initialization checks (module import + callable `register(api)` requirement) before a plugin can become active.
- Added tests for assignment-based runtime gating and initialization failure behavior.
- Added Platform Admin React UI support for plugin discovery status, validation visibility, capability/permission inspection, and platform approval toggling.
- Added Tenant Admin React UI support for plugin enablement, JSON config editing, and assignment rule management (`role` and `user`) against the tenant plugin API.
- Added plugin API client bindings and shared frontend types so plugin state is consumable via bootstrap payloads and dedicated plugin endpoints.
- Added DB-backed plugin ZIP installation from Platform Admin (`/api/platform/plugins`) so plugins no longer depend on repo-shipped filesystem bundles.
- Added persisted plugin bundle artifact fields (filename, sha256, blob) and runtime materialization for uploaded plugins before runtime resolution.
- Added runtime support for multiple manifest roots so uploaded bundles can be prioritized while keeping disk discovery as optional fallback.
