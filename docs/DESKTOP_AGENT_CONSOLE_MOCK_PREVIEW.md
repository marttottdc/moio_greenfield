# Desktop Agent Console Mock Preview

This repository now exposes the original desktop agent console UI under a separate preview namespace inside the active frontend.

## Routes

- `/`
  - Entry surface with two buttons:
    - main platform SPA
    - desktop agent console preview
- `/desktop-agent-console/`
  - Original Access Hub UI
- `/desktop-agent-console/console`
  - Original Agent Console UI
- `/desktop-agent-console/platform-admin`
  - Original Platform Admin UI
- `/desktop-agent-console/tenant-admin`
  - Original Tenant Admin UI

## Current behavior

These surfaces are mounted for review and navigation only.

They are not yet wired to the new Django backend contracts.

The preview currently uses mocked client-side transport:

- mocked `fetch` for platform, tenant, and auth endpoints
- mocked `WebSocket` transport for the agent console
- seeded `localStorage` session state so the original apps boot consistently

## Purpose

This is intended to let us:

- inspect the original UX in-place
- compare flows against the active platform frontend
- recover workspace, tenant, and platform administration concepts before real backend integration

## Important limitations

- The console responses are synthetic preview messages.
- Platform admin and tenant admin mutations are local mock mutations only.
- No real tenant isolation or runtime execution happens through these preview routes.
- The active platform SPA remains the source of truth for production behavior.

## Main files

- `frontend/client/src/App.tsx`
- `frontend/client/src/pages/index-entry.tsx`
- `frontend/client/src/pages/desktop-agent-console-access-hub.tsx`
- `frontend/client/src/pages/desktop-agent-console-console.tsx`
- `frontend/client/src/pages/platform-admin-legacy.tsx`
- `frontend/client/src/pages/tenant-admin-legacy.tsx`
- `frontend/client/src/legacy-admin/mock-preview.ts`
- `frontend/client/src/legacy-admin/mock-console.ts`
- `frontend/client/src/legacy-admin/vendor/components/AccessHubApp.tsx`
- `frontend/client/src/legacy-admin/vendor/components/AgentConsoleApp.tsx`
- `frontend/client/src/legacy-admin/vendor/components/PlatformAdminApp.tsx`
- `frontend/client/src/legacy-admin/vendor/components/TenantAdminApp.tsx`

## Next step

Replace the mock transport progressively with real backend endpoints:

1. platform admin bootstrap and tenant catalog
2. tenant admin bootstrap and workspace configuration
3. agent console websocket/runtime integration
