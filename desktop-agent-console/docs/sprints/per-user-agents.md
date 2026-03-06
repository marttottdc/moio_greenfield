# Sprint: Per-User Agents and Shared Workspaces

## Goal

Shift the runtime model away from treating `Workspace` as the default unit of identity, isolation, and agent configuration.

Keep `Workspace` as an explicit collaboration surface for shared sessions, while making user identity, user-level inputs, and per-user agent behavior first-class.

## Why This Sprint Exists

The current design overloads `Workspace` with too many responsibilities:

- shared collaboration context
- prompt/profile container
- default model/tool configuration container
- storage boundary for sessions and artifacts

That makes privacy, per-user behavior, and clean permissioning harder than they need to be.

## Product Direction

Workspaces remain available, but they become opt-in shared spaces for coworkers.

The default mental model becomes:

- each user has an individualized agent context
- each user input is attributed to that user
- tenant admins decide what users can access
- a workspace can be used when users intentionally collaborate in a shared thread
- everything written into a shared workspace thread is visible to all of that workspace's participants

## Core Design Decisions

1. Shared session, individual authorship

Even in a shared workspace session, every message must record who authored it so collaborators can tell who wrote what.

2. Shared thread visibility is not per viewer

Shared workspace transcript, event log, summaries, and artifacts are visible to all participants in that workspace thread.

3. Agent resolution is per user, not per workspace

The active user and the selected profile determine prompt, tools, credentials, and defaults for that turn.

4. Authorization is enforced at turn execution time

Tool access and credential resolution must run under the identity of the user who initiated the turn, not under a generic workspace identity.

5. Workspace is collaboration scope, not the default policy scope

A workspace can add shared context, but it should not be the primary container for every user's personal runtime behavior.

6. Tenant admin remains the policy owner

Tenant admins define which capabilities, profiles, and plugins users or roles may use.

## Target Runtime Model

The system should resolve an effective agent configuration from:

- tenant
- user
- optional workspace
- selected agent profile (or default profile)

This resolved configuration should determine:

- system prompt additions
- model vendor/model defaults
- allowed tools
- enabled plugins
- available credentials
- turn-time authorization behavior for the initiating user

## Key Invariant

The runtime must be able to answer this deterministically:

"Given tenant + user + optional workspace + selected profile, what exact agent configuration is active for this request?"

If that answer is not deterministic, both permissioning and plugin activation will become unreliable.

## Intended Domain Model

The exact schema can change, but the architecture should converge toward:

- `AgentProfile`: reusable definition of prompt, defaults, tool policy, plugin entitlements
- user-to-profile assignment or selection
- user-scoped session authorship
- explicit shared workspace membership / participation
- tenant-level policy controlling what profiles and capabilities may be assigned

`Workspace` should remain available for shared threads and shared artifacts, but it should not be the only place where agent behavior is configured.

## Expected Backend Changes

The current runtime cache is effectively keyed by `tenant:workspace`.

That is useful for shared collaboration state, but it is too coarse for per-user agent resolution and turn-time authorization.

The new architecture should move toward:

- shared runtime infrastructure where practical
- per-request user context resolution
- user/profile-aware tool and prompt assembly at execution time

We should avoid a full backend instance per user unless a specific isolation need requires it.

## Data Separation Guidance

We need a deliberate split between:

- shared data: collaborative session timeline, shared workspace artifacts, shared summaries, shared automations where applicable
- user-specific data: authorship identity, personal credentials, personal defaults, personal entitlements, profile selection

Important: user-specific authorization does not imply per-viewer filtering inside a shared workspace thread. Shared workspaces behave like group conversations: shared is shared.

This sprint should prioritize defining those boundaries before implementation spreads more workspace-scoped assumptions through the codebase.

## Out of Scope For This Sprint

- full plugin implementation
- background service lifecycle changes
- broad runtime sandboxing
- redesigning every existing model at once

The purpose of this sprint is to establish the identity and configuration model that later work can build on.

## Open Questions

- Should a shared workspace allow multiple active agent profiles in the same thread?
- How should per-user memory interact with shared workspace artifacts outside the shared thread?
- What is the minimum schema change needed to start recording message authorship cleanly?
- Which existing workspace settings should move to `AgentProfile`, and which should remain on `Workspace`?
- How should the UI explain tool denials caused by initiator-specific permissions or credentials?

## Implementation Checklist

- Audit current workspace-scoped assumptions in models, runtime assembly, session storage, and API payloads.
- Define the minimal new request context contract: tenant, user, optional workspace, selected profile.
- Introduce message authorship fields so shared sessions can show exactly which user wrote each entry.
- Keep workspace transcript, event log, and summary shared across workspace participants.
- Define `AgentProfile` and the resolution rules for defaults, overrides, and tenant-admin policy constraints.
- Move agent-facing defaults out of `Workspace` where they are really profile concerns.
- Resolve tool permissions and credentials using the initiating user's auth context on each run.
- First implementation cut: enforce config-driven `tools.admin_only` capabilities against the initiating tenant role before tool schema exposure and before tool execution.
- When an integration declares user-scoped auth, runtime resolution must bind `api.run` to the initiating user's credential record for that turn.
- Decide which data stays shared in a workspace and which user-specific data must live outside the shared thread.
- Refactor runtime/tool/prompt resolution so the effective agent configuration is assembled per request, not inferred only from workspace.
- Add compatibility rules so existing workspace-only flows still work during rollout.
- Add tests for deterministic agent resolution, shared-session authorship, and initiator-scoped permission boundaries.
- Add diagnostics that explain which profile, policy, and capabilities were active for a given run.

## Suggested Branch

`codex/per-user-agents`
