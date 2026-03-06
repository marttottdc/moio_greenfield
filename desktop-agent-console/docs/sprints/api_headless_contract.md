# API Headless Contract (Enforced Defaults)

These defaults are now enforced at framework level and should be used for all new REST endpoints.

## Response format

- Success list:
  - `data`: list payload
  - `meta`: pagination/filter metadata
  - `links`: navigation links when paginated
- Success item:
  - `data`: object payload
- Error:
  - `error.code`
  - `error.message`
  - `error.details`
  - `status`
  - optional `request_id`

Global handler: `webchat_django.api_errors.api_exception_handler`.

## Pagination

- Default pagination class: `LimitOffsetPagination`
- Params:
  - `limit` (server-capped)
  - `offset`
- Defaults configured in DRF settings (`PAGE_SIZE=50`).

## Filtering / Search / Ordering

- Free text search param: `q`
- Ordering param: `sort`
- Keep exact filters explicit and field-specific (`status=`, `created_at_gte=`, etc.).

## Endpoint catalog

`GET /api/v1/meta/endpoints/` exposes machine-usable endpoint contracts:

- searchable: `q`
- filterable: `module`, `method`, `tag`, `path`, `requires_workspace`, `requires_body`
- paged: `limit`, `offset`
- per endpoint includes:
  - auth requirements
  - path/query/body contract
  - response contract
  - curl `call_example`

