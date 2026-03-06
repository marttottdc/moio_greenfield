# Moio Platform Public API Reference

**Audience:** Frontend, automation, and partner teams building UI integrations or external services.
**Status:** Public-ready snapshot derived from internal module specs (v1.1).
**Primary Goal:** Provide a single, versioned contract that UI pipelines can target without exposing internal-only implementation detail.

---

## 1. Access & Versioning

| Environment | Base URL                    | Notes |
|-------------|-----------------------------|-------|
| Production  | `https://api.moio.ai/api/v1` | Stable namespace consumed by customer-facing UIs. |
| Staging     | `https://staging.moio.ai/api/v1` | Mirrors prod data models; use for QA and CI smoke tests. |

- All endpoints follow REST semantics over HTTPS and exchange JSON payloads encoded in UTF-8.
- Breaking changes trigger a new versioned namespace (`/api/v2/...`). Minor, backwards-compatible updates are released via additive fields flagged in the changelog.
- Every request must include `X-Moio-Client-Version` so release engineering can correlate CI builds with platform capabilities.

---

## 2. Authentication & Security

- The platform issues JWT Bearer tokens backed by Django Allauth sessions.
- Clients authenticate via `POST /auth/login`, receive `access_token`, `refresh_token`, and optional `session_token` for correlating browser sessions.
- Access tokens expire after 15 minutes. Refresh tokens rotate on each `POST /auth/refresh` call; the previous refresh token becomes invalid.
- Include `Authorization: Bearer <access_token>` on protected endpoints.

```http
POST /auth/login
Content-Type: application/json

{"username": "demo@moio.ai", "password": "••••••••"}
```

```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "4b8af6d2-...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "full_name": "Demo Owner",
    "role": "admin"
  }
}
```

### Standard Headers
- `Authorization: Bearer <token>` – Required on every non-auth endpoint.
- `X-Moio-Client-Version` – Semantic version of the consuming UI build.
- `X-Moio-Tenant` – Optional tenant override for multi-tenant admins.

### Rate Limits & Throttling
- Authenticated clients receive 120 requests per minute per tenant.
- Burst traffic exceeding 150 req/min will receive `429 Too Many Requests` with `Retry-After` header.

---

## 3. Global Conventions

| Concern | Contract |
|---------|----------|
| Pagination | Offset-based pagination using `?page=` and `?page_size=`, response includes `count`, `next`, `previous`, `results`. |
| Filtering | Query params such as `?search=`, `?status=`, `?ordering=-created_at`. Modules extend these with documented filters. |
| Errors | All errors return `{ "error": "code", "message": "Human readable" }` with standard HTTP status. Validation errors add a `fields` map. |
| Webhooks | Outbound events (campaign sends, flow executions) are delivered from `hooks.moio.ai` with HMAC-SHA256 signatures derived from the tenant secret. |

---

## 4. Module Overview

The API is modular; each section below summarizes the contract UI teams rely on. Use these summaries to scaffold SDK clients or CI mocks, then consult the per-module OpenAPI fragments (links reference internal repos) when deeper field-level detail is required.

### 4.1 Platform Experience
Purpose-built endpoints for content delivery, localization, and conversational widgets that power the marketing site and logged-in portal.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/content/pages/{slug}` | Resolve published page with locale-aware fallbacks and cache hints. |
| GET | `/content/navigation` | Fetch menu hierarchy plus feature flags for gated experiences. |
| POST | `/conversations/session` | Initialize AI assistant session and return WebSocket token for live chat. |
| GET | `/engagement/topics` | Retrieve trending topics, recaps, and bookmarking metadata. |
| POST | `/meetings/slots` | Propose availability windows for embedded scheduling UI. |

Frontend alignment: dynamic CMS surfaces, localization switcher, conversational side panels, and meeting booking modals.

### 4.2 Core Services
Authentication, user preferences, and integration management reused by all other modules.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Exchange credentials for JWT pair. |
| POST | `/auth/refresh` | Rotate tokens when the access token expires. |
| POST | `/auth/logout` | Revoke active session. |
| GET | `/auth/me` | Return profile, role, and tenant metadata. |
| GET | `/settings/preferences` | Retrieve per-user UI, notification, and locale preferences. |
| PUT | `/settings/preferences` | Update preferences; partial updates supported. |
| GET | `/settings/integrations` | Enumerate connected services (WhatsApp, Gmail, OpenAI, etc.). |
| POST | `/settings/integrations/{id}/connect` | Kick off OAuth/handshake for the integration selected in the UI. |

Release guidance:
- Adding a new integration requires a new `type` constant plus OAuth metadata; no breaking UI changes when `capabilities` are additive.
- Admin console tables consume `GET /settings/integrations` and expect `status`, `last_synced_at`, and `error` fields.

### 4.3 Contacts & Deals
Classic CRM records with Kanban pipeline tracking.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/contacts` | List contacts (supports search, tag, owner filters). |
| POST | `/contacts` | Create contact with basic profile fields plus custom attributes. |
| GET | `/contacts/{id}` | Retrieve full contact including timeline snippets. |
| PUT | `/contacts/{id}` | Update contact metadata. |
| DELETE | `/contacts/{id}` | Soft-delete and archive contact. |
| POST | `/contacts/import` | Upload CSV, returns async import job id. |
| GET | `/contacts/export` | Stream CSV export filtered by current query params. |
| GET | `/deals` | List deals grouped by pipeline stage. |
| POST | `/deals` | Create deal with stage, owner, and monetary value. |
| PATCH | `/deals/{id}` | Update stage or custom fields used by Kanban UI. |

Frontend alignment: contacts list, deal Kanban board, contact detail drawer, import/export wizard. CI smoke tests should validate pagination, filtering, and CSV job lifecycle.

### 4.4 Communications
Unified messaging inbox covering WhatsApp, email, and SMS.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/communications/chats` | List conversations sorted by recent activity. |
| GET | `/communications/chats/{id}/messages` | Fetch paginated message history. |
| POST | `/communications/chats/{id}/messages` | Send outbound message; accepts text, attachments, or template payloads. |
| GET | `/communications/channels` | Return enabled channels and connection health. |
| POST | `/communications/channels/{id}/test` | Trigger channel health check for settings UI. |

Frontends should open a WebSocket to receive live message events; fallback polling every 10 seconds keeps CI pipelines deterministic when sockets are unavailable.

### 4.5 Campaigns
Marketing automation for broadcast and scheduled outreach.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/campaigns` | List campaigns with status, channel, and performance metrics. |
| POST | `/campaigns` | Create draft campaign (audience, content, channel config). |
| GET | `/campaigns/{id}` | Retrieve campaign detail including targeting rules. |
| POST | `/campaigns/{id}/send` | Launch immediate send or confirm a scheduled send. |
| GET | `/campaigns/{id}/analytics` | Return delivery, open, click, and reply metrics. |
| GET | `/templates` | List reusable content templates; used by builder UI. |

CI guardrails: verify template rendering, ensure send endpoints require confirmation flag for production, and simulate analytics responses with deterministic fixture values.

### 4.6 Flows & Automation
Workflow builder and AI automation runtime.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/flows` | List workflows with status, trigger type, and last run info. |
| POST | `/flows` | Create workflow; accepts JSON graph exported from the builder. |
| GET | `/flows/{id}` | Fetch workflow definition plus audit metadata. |
| PUT | `/flows/{id}` | Replace workflow definition. |
| POST | `/flows/{id}/activate` | Activate workflow after validation. |
| POST | `/flows/{id}/test` | Execute workflow in sandbox mode and return logs for CI validation. |
| GET | `/flows/runs` | Paginated history of past executions with status and duration. |

Automation-specific guidance:
- Custom script nodes must declare runtime (`python3.11`, `node18`) and timeouts to keep executions deterministic.
- AI agent nodes expose `model`, `prompt_template`, and `guardrails` arrays so the UI can preview expected behavior before activation.

---

## 5. CI & Release Workflow

1. **Schema Source of Truth** – The OpenAPI bundle is generated from these modules via `manage.py generate_openapi`. Commit the resulting `openapi-public.json` for consumers.
2. **Contract Testing** – UI pipelines should run Postman/Newman or pytest contracts against staging using the endpoints above. Required smoke suite:
   - Auth login, refresh, logout cycle
   - CRUD for contacts & deals
   - Send + fetch campaign analytics
   - Flow creation, activation, and sandbox test
3. **Changelog Management** – Document field additions or behavior tweaks in `docs/API_ADDITIONS.md`; summarize public-safe entries in `docs/MOIO_PUBLIC_API_REFERENCE.md#changelog`.
4. **Mocking Strategy** – Use the JSON fixtures under `attached_assets/api_mocks/` (mirrors real response shapes without sensitive data) for offline development and Storybook previews.

---

## 6. Changelog (Public Extract)

| Date | Change |
|------|--------|
| 2025-02-04 | Added `POST /communications/channels/{id}/test` for proactive channel diagnostics. |
| 2025-01-15 | Introduced `GET /flows/runs` execution history endpoint to support automation analytics. |
| 2024-12-10 | Campaign analytics responses now include `reply_rate` in addition to opens/clicks. |
| 2024-11-01 | Initial public snapshot of v1.1 modules. |

---

## 7. Support & Next Steps

- Request access keys or tenant secrets via platform operations (`platform-ops@moio.ai`).
- Report bugs by opening a ticket in Jira project **PLATAPI** with reproduction steps and endpoint traces.
- For upcoming modules (Recruiter, Assessments), follow the same contract templates; publish at least 2 weeks before UI launch to give integrators time to align CI suites.
