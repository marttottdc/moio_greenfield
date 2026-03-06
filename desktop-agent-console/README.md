# Moio

Django-based Python agent runtime with:

- one browser chat box (`/`)
- local agent loop (no external gateway dependency)
- local tools for files/web/scraping/resources/shell/code/docker
- dynamic tool creation (`tools.create`) and tool discovery (`tools.list`)
- optional pip installs from the agent loop (`packages.install`)
- encrypted local vault for sensitive values (`vault.set`, `vault.get`, `vault.list`, `vault.delete`)
- local skills loading (`SKILL.md` discovery)
- local session persistence (`sessions_dir`)
- OpenAI-compatible model backend

## What "full decoupling" means here

This project does not call an external gateway RPC method.
It runs its own:

- chat loop
- tool execution loop
- skill loading + prompt injection
- session storage/history
- websocket UI transport

## Runtime

- Python 3.11+
- `OPENAI_API_KEY` (or `model.api_key` in config)

## Install

```bash
cd /Users/martinotero/moio_projects/moio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Configure

```bash
cp config.example.toml config.toml
```

Set API key (recommended via env):

```bash
export OPENAI_API_KEY="<your-key>"
```

Set vault passphrase (required for `vault.*` tools):

```bash
export REPLICA_VAULT_PASSPHRASE="<strong-passphrase>"
```

Adjust `workspace_root`, `skills.directories`, and model fields in `config.toml` as needed.
If you want runtime package installs from the agent, set `tools.package_install_enabled = true`.

## Run

```bash
source .venv/bin/activate
python manage.py migrate
moio --config /Users/martinotero/moio_projects/moio/config.toml
```

Alternative via Uvicorn:

```bash
source .venv/bin/activate
REPLICA_MODEL_API_KEY="<your-key>" uvicorn webchat_django.asgi:application --host 127.0.0.1 --port 8088
```

`moio-django` remains available as a compatibility alias for the same Django runtime.

Open:

- frontend UI: `http://127.0.0.1:5174`
- backend API: `http://127.0.0.1:8088`

Workspace routing:

- default workspace: `main`
- access hub entrypoint: `http://127.0.0.1:5174/`
- agent console route: `http://127.0.0.1:5174/console/?workspace=sales`
- optional tenant parameter (Sprint 3.5): `http://127.0.0.1:5174/console/?tenant=acme&workspace=sales`
- each workspace gets isolated sessions/vendors/vault/custom-tools paths
- Django runtime now defaults to DB-backed session memory (`REPLICA_DJANGO_SESSION_STORE=db`); set `REPLICA_DJANGO_SESSION_STORE=file` to keep filesystem session JSON files.

## Deployment

This repo now uses:

- local runtime as the preprod/staging environment
- Kubernetes as the production environment

This repo includes split production deployment scaffolding:

- backend image: `Dockerfile.backend`
- frontend image: `frontend/react/Dockerfile`
- Helm chart: `infra/charts/moio-stack`
- GitHub Actions: `.github/workflows` (production only)

The intended production shape is:

- `backend` Django ASGI deployment
- `worker` Celery worker deployment
- `scheduler` Celery beat deployment
- `frontend` React static deployment

Production uses separate public ingresses:

- `https://moio.ai` for the React SPA
- `https://api.moio.ai` for Django API, websocket, media, and health checks

Frontend-owned browser routes are:

- `/` access hub
- `/console/` agent console
- `/platform-admin/` platform admin
- `/tenant-admin/` tenant admin

Backend-owned routes are:

- `/api/*`
- `/ws`
- `/media/*`
- `/healthz`

The Helm chart assumes Postgres and Redis already exist in the cluster and are injected from a Kubernetes Secret already present in the target namespace (`secrets.existingSecretName`, set to `moio-runtime-secrets` in the environment values):

- `DATABASE_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `DJANGO_SECRET_KEY`
- optional `OPENAI_API_KEY` fallback
- `REPLICA_VAULT_PASSPHRASE`

GitHub Actions only need kubeconfig access. They do not pass runtime app secrets anymore; the in-cluster secret is referenced by the chart.

Deploys are gated by automated validation in GitHub Actions. Backend workflows run `python manage.py check` and `python manage.py test webchat_django.chatui.tests -v 2` before build/deploy. Frontend workflows run `npm run build` before build/deploy.

The frontend production workflow defaults the SPA runtime endpoints to:

- `VITE_API_ORIGIN=https://api.moio.ai`
- `VITE_WS_BASE_URL=wss://api.moio.ai/ws`

You can still override those with the `PROD_API_ORIGIN` and `PROD_WS_BASE_URL` repository variables if the production hostnames change.

Helm deploys use `--rollback-on-failure --wait`, and the chart includes a pre-install/pre-upgrade migration Job. If migrations fail, the release fails and the rollout is not applied. When `DJANGO_TENANTS_ENABLED=1`, the migration hook runs:

- `python manage.py migrate_schemas --shared --noinput`
- `python manage.py migrate_schemas --tenant --noinput`

Local preprod uses the normal local runtime:

- start local Postgres/Redis with `docker-compose -f docker-compose.db.yml --env-file .env.db up -d` when needed
- run Django locally with `moio --config ./config.toml` or `python -m uvicorn webchat_django.asgi:application --host 127.0.0.1 --port 8088`
- run the frontend locally with `cd frontend/react && npm run dev` when iterating on the SPA

### Local test env (Docker DB + Redis + backend + frontend + ngrok)

Use the helper script to boot a full local dev stack:

```bash
cd /Users/martinotero/moio_projects/moio
./scripts/dev-local-env.sh all
```

Default tunnel setup is:

- `https://moio.ngrok.dev -> http://127.0.0.1:8093`
- frontend runtime API origin: `https://moio.ngrok.dev`
- frontend runtime websocket base: `wss://moio.ngrok.dev/ws`

Useful commands:

```bash
./scripts/dev-local-env.sh db-up
./scripts/dev-local-env.sh migrate
./scripts/dev-local-env.sh backend
./scripts/dev-local-env.sh frontend
./scripts/dev-local-env.sh db-down
```

If Postgres/Redis are already running, start only app services:

```bash
NGROK_URL=https://moio.ngrok.dev ./scripts/dev-local-env.sh apps
```

`apps` and `all` now stream backend/frontend logs in your terminal.
If ports are busy, the script fails fast and asks you to override `BACKEND_PORT` or `FRONTEND_PORT`.

Optional frontend local env template:

```bash
cp frontend/react/.env.local.example frontend/react/.env.local
```

If local ports are already in use, override them per command:

```bash
REDIS_PORT=6390 POSTGRES_PORT=54339 ./scripts/dev-local-env.sh db-up
```

The helper sets a local fallback `REPLICA_MODEL_API_KEY=local-dev-placeholder-key` so backend boot does not fail if you have no LLM key yet. Override with your real key when needed.

### Full local stack in Docker (backend + frontend + db + redis)

Dev-only workflow. Production stays on Kubernetes/Helm.

Use the full compose stack when you want both app services containerized too:

```bash
cd /Users/martinotero/moio_projects/moio
cp .env.local-stack.example .env.local-stack
docker-compose -f docker-compose.local-stack.yml --env-file .env.local-stack up -d --build
```

Check status/logs:

```bash
docker-compose -f docker-compose.local-stack.yml --env-file .env.local-stack ps
docker-compose -f docker-compose.local-stack.yml --env-file .env.local-stack logs -f moio-backend moio-frontend
```

Stop stack:

```bash
docker-compose -f docker-compose.local-stack.yml --env-file .env.local-stack down
```

If frontend should call backend through ngrok (`https://moio.ngrok.dev -> http://127.0.0.1:8093`), set in `.env.local-stack` before `--build`:

```bash
FRONTEND_API_ORIGIN=https://moio.ngrok.dev
FRONTEND_WS_BASE_URL=wss://moio.ngrok.dev/ws
```

### One command local test launcher (db/redis in Docker + backend/frontend local)

Recommended for zsh (single practical workflow):

```bash
cd /Users/martinotero/moio_projects/moio
POSTGRES_PORT=54339 REDIS_PORT=6390 BACKEND_PORT=8093 FRONTEND_PORT=5177 START_NGROK=1 NGROK_URL=https://moio.ngrok.dev ./scripts/dev.zsh up
```

Then:

```bash
./scripts/dev.zsh logs
./scripts/dev.zsh status
./scripts/dev.zsh down
```

Notes:

- ngrok is for frontend only (`https://moio.ngrok.dev -> http://127.0.0.1:5177`)
- frontend API mode defaults to proxy (`FRONTEND_API_MODE=proxy`)
- Vite proxy target is controlled by `BACKEND_HOST` + `BACKEND_PORT`
- optional local env file: `.env.dev.local` (loaded automatically by `scripts/dev.zsh`)

```bash
cp .env.dev.local.example .env.dev.local
```

Legacy bash launcher is still available:

```bash
POSTGRES_PORT=54339 REDIS_PORT=6390 BACKEND_PORT=8093 FRONTEND_PORT=5177 FRONTEND_API_MODE=proxy START_NGROK=1 NGROK_URL=https://moio.ngrok.dev ./scripts/run-dev-with-ngrok.sh
```

## Media storage (conversation-scoped)

All uploaded files and generated files (`files.write`) are now mirrored into a conversation media folder:

- local path pattern: `.data/media/<tenant>/<workspace>/<session>/<run>/<uploads|generated>/<filename>`
- download endpoint: `/media/<session>/<run>/<uploads|generated>/<filename>`

By default media is stored locally. To also host media on S3:

```bash
export REPLICA_MEDIA_BACKEND=s3
export REPLICA_S3_BUCKET=<bucket-name>
export REPLICA_S3_REGION=<region>                 # optional
export REPLICA_S3_ENDPOINT_URL=<endpoint-url>     # optional (S3-compatible providers)
export REPLICA_S3_ACCESS_KEY_ID=<access-key>      # optional (if not using instance role)
export REPLICA_S3_SECRET_ACCESS_KEY=<secret-key>  # optional (if not using instance role)
export REPLICA_S3_PREFIX=webchat-media            # optional
export REPLICA_S3_PUBLIC_BASE_URL=<cdn-or-bucket-base-url>  # optional
export REPLICA_S3_PRESIGN_SECONDS=86400           # optional, used when no public base URL
```

If `REPLICA_MEDIA_BACKEND=s3` is enabled, tool outputs include `downloadUrl` (S3 URL when available, local `/media/...` fallback otherwise).

## Supported client actions

The frontend websocket (`/ws`) supports:

- `init`
- `refresh_resources`
- `chat_history`
- `chat_summary`
- `chat_usage`
- `chat_sessions_list`
- `chat_session_create`
- `vendors_list`
- `vendor_upsert`
- `vendor_delete`
- `vendor_models`
- `api_connections_list`
- `api_connection_upsert`
- `api_connection_delete`
- `send_message`
- `abort`

## Tooling notes

- `resource.read` supports text, html, csv/tsv, pdf, docx, xlsx, image metadata, and audio metadata/transcription.
- dynamic tools are persisted in `tools.dynamic_tools_dir` as JSON files and auto-loaded on startup.
- `web.fetch`, `web.extract`, `web.scrape`, and URL mode in `resource.read` support `prefer_curl` and `verify_ssl`.
- `web.request` supports API-style calls (method, headers, query, json/body) without requiring extra Python packages.
- `api.run` executes workspace-scoped API connections with auth handling (`none`, `bearer`, `api_key_header`, `api_key_query`, `basic`, `oauth2_client_credentials`).
- `api.run` supports `rest`, `graphql`, and `soap` protocol modes.
- `vault.*` values are encrypted at rest in `tools.vault_file`; tool event args/results are redacted for vault values.
- `memory.record`, `memory.search`, and `memory.recent` expose persistent workspace/session artifact memory to the agent.

Server emits:

- `chat_event` (final/error/aborted)
- `agent_event` (tool stream events)
- `gateway_state` (always connected=true for local runtime)

## Local Postgres container

Start local Postgres (+ Redis helper) for tenant mode:

```bash
cd /Users/martinotero/moio_projects/moio
cp .env.db.example .env.db
docker-compose -f docker-compose.db.yml --env-file .env.db up -d
```

Use Postgres + django-tenants:

```bash
source .venv/bin/activate
export DJANGO_TENANTS_ENABLED=1
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=54329
export POSTGRES_DB=moio
export POSTGRES_USER=moio
export POSTGRES_PASSWORD=moio
export REPLICA_VAULT_PASSPHRASE="<strong-stable-passphrase>"
python manage.py migrate_schemas --shared
```

Create tenant + domain (example):

```bash
python manage.py shell -c "from webchat_django.tenancy.models import Client,Domain; t=Client.objects.create(name='Acme',slug='acme',schema_name='acme'); Domain.objects.create(domain='acme.localhost',tenant=t,is_primary=True)"
python manage.py migrate_schemas --tenant
```

Or use management commands:

```bash
python manage.py bootstrap_tenant --schema public --slug public --name Public --domain localhost
python manage.py bootstrap_tenant --schema acme --slug acme --name Acme --domain acme.localhost
python manage.py list_tenants
```

## Extract To A New Repo

This folder can be split as an independent repository:

```bash
cd /Users/martinotero/moio_projects
git subtree split --prefix=moio -b codex/moio-split
```

Push split branch to a new repo:

```bash
git push <new-remote-url> codex/moio-split:main
```
