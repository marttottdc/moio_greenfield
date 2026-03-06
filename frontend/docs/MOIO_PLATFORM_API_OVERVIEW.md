# Moio Platform API Overview

All API endpoints documented here live under the `https://tu-backend.com/api` namespace and require Bearer token authentication. The platform now resolves page content, layouts, and conversational history directly from storage so that editors can publish changes without redeployments.

## Content Delivery & Localization

### `GET /content/pages/{slug}`
Fetch the resolved page definition (sections and blocks) for the requested locale.

| Query | Description |
| --- | --- |
| `locale` | Optional BCP-47 language tag (for example `en`, `en-US`, `es`). When omitted the page default locale is used. |

Each block in the response payload contains the following information:

- `type` – one of the supported discriminated union types: `hero`, `rich_text`, `feature_list`, `cta`.
- `payload` – validated JSON payload matching the block type contract (see table below).
- `locale.requested` – normalized locale requested by the client.
- `locale.resolved` – actual locale returned after applying block-level or section-level fallbacks.
- `locale.fallbackApplied` – `true` when a fallback was required.
- `locale.fallbackChain` – ordered locales evaluated while resolving the block.

Caching strategy: `Cache-Control: private, max-age=120` and `Vary: Authorization, Accept-Language` so intermediate caches can store per-user locale variants while honoring authentication.

| Block type | Payload contract |
| --- | --- |
| `hero` | `{ "headline": string, "cta": { "label": string, "href": string }, "subheadline?": string, "image?": string }` |
| `rich_text` | `{ "markdown": string }` |
| `feature_list` | `{ "features": [{ "title": string, "description": string, "icon?": string }, ...] }` |
| `cta` | `{ "title": string, "primaryCta": { "label": string, "href": string }, "secondaryCta?": { "label?": string, "href?": string }, "body?": string }` |

### `GET /content/sitemap`
Return the canonical hierarchy of pages and sections, including layout hints, available locales, fallback locales, and block keys. Responses are cacheable with `Cache-Control: private, max-age=300` and `Vary: Authorization, Accept-Language`, enabling edge caches to memoize structures per tenant and locale while respecting authentication boundaries.

## Session & Personalization

### `POST /session`
Create or resume a visitor session. Referral metadata and engagement counters are persisted so subsequent requests share the same `sessionId`.

### `GET /session/{sessionId}/analytics`
Return aggregated metrics (topics visited, likes, engagement score) for the supplied session.

## Conversational Experiences

### `POST /agent/chat`
Append a user + assistant exchange to the normalized `conversation_messages` table. The response includes the assistant message, follow-up suggestions, the `conversationId`, and `messageIndex` (the assistant message's session-scoped sequence number). Session totals and last-engaged timestamps update automatically.

### `GET /agent/conversations/{sessionId}`
List conversation messages for a session. Supports the query parameters `topic` (topic slug), `date` (`YYYY-MM-DD`), `page` (1-based), and `pageSize` (1–100). Results are ordered newest-first and include conversation metadata for pagination.

### `DELETE /agent/conversations/{sessionId}`
Delete conversation messages for the supplied filters. Remaining empty conversations are removed automatically to support GDPR cleanup workflows.

### Conversation Storage Model

- `conversation_messages` is keyed by `(session_id, conversation_id, conversation_date, topic_id)` with per-conversation and per-session sequence numbers to support efficient pagination and message reactions.
- Likes reference `conversation_messages` through `messageIndex` and a direct foreign key, ensuring consistent cleanup.

## Content Analytics & Engagement

### `POST /likes`
Toggle a like for the assistant message identified by `messageIndex`. The index refers to `conversation_messages.session_sequence` for the provided session. The endpoint automatically associates the like with the message and topic.

### `POST /email/send`
Generate and log an email recap of the latest assistant response (optional marketing summary).

### `POST /whatsapp/send`
Prepare or dispatch a WhatsApp conversation recap, returning a deep link or confirmation payload.

### `POST /track/topic-visit`
Log each topic interaction with a timestamp for analytics and personalization.

## Meeting Scheduling

### `POST /meeting/schedule`
Validate attendee details, book the meeting in the requested provider, and return confirmation messaging plus an optional calendar URL.

## Topics Catalogue (Deprecated)

- `GET /topics`
- `GET /topics/{slug}`

These legacy endpoints continue to serve static marketing content but are slated for removal once all consumers migrate to the dynamic page/section/block workflow described above.
