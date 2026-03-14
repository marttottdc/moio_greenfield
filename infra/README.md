# Moio Greenfield – Infra y deployment

Modelo de deployment replicado de **moio_platform**: backend, frontend y workers en Helm; base de datos, Redis y PgBouncer **externos** al cluster.

## Recursos externos (fuera del Helm)

- **PostgreSQL**: servidor gestionado o self-hosted (no está en el chart).
- **Redis**: instancia externa (no está en el chart).
- **PgBouncer**: connection pooler externo; en prod/preprod la `DATABASE_URL` apunta al host:puerto de PgBouncer (p. ej. `prod-pgbouncer:6432`), no directo a Postgres.

## Chart del stack (backend + workers)

- **Chart**: `infra/charts/moio-greenfield-stack/`
- **Incluye**:
  - **Backend**: deployment + service (Hypercorn, puerto 8010).
  - **Workers Celery**: high, medium, low, flows (mismas colas que moio_platform).
  - **Scheduler**: Celery beat con `django_celery_beat.schedulers:DatabaseScheduler`.
  - ConfigMap (`DATABASE_URL`, `REDIS_URL`, `APP_NAME`), Secret, Ingress.

No incluye Postgres, Redis ni PgBouncer; se configuran por `config.database_url` y `config.redis_url` en los values.

## Frontend (UI)

- **Chart**: `frontend/deploy/chart/` (moio-frontend).
- Despliegue independiente del stack de backend (otra release Helm o mismo namespace con otro release).

## Despliegue

1. Crear namespace y secret de registro si aplica:
   ```bash
   kubectl create namespace moio-greenfield
   kubectl create secret docker-registry registry-4 --from-file=.dockerconfigjson=... -n moio-greenfield
   ```

2. Valores de entorno (prod): usar `infra/environments/prod.yaml`. Sustituir en ese archivo (o vía `--set`) las URLs reales de:
   - `config.database_url` → PgBouncer (ej. `postgres://user:pass@prod-pgbouncer:6432/moio_greenfield`)
   - `config.redis_url` → Redis (ej. `redis://prod-redis:6379/1`)
   - `secrets.secret_key` (y otros secretos) en un values file secreto o sealed secrets.

3. Instalar el stack backend + workers:
   ```bash
   helm upgrade --install moio-greenfield-stack ./infra/charts/moio-greenfield-stack \
     -f infra/environments/prod.yaml \
     -n moio-greenfield \
     --set secrets.secret_key="$(openssl rand -base64 48)"
   ```

4. Instalar el frontend (si aplica):
   ```bash
   helm upgrade --install moio-frontend ./frontend/deploy/chart -n moio-greenfield -f frontend/deploy/chart/values.yaml
   ```

## Entornos

- **preprod**: `infra/environments/preprod.yaml` (1 replica por componente, URLs preprod).
- **prod**: `infra/environments/prod.yaml` (réplicas tipo moio_platform: backend 2, worker-high 4, etc.).

Ajustar `ingress.host`, `ingress.tlsSecret` e `image.repository`/`image.tag` según tu registro y dominio.

## GitHub Actions CI

- **Build Backend & Deploy to Preprod** (`.github/workflows/build-backend-deploy-preprod.yml`): en cada push a `main` construye la imagen desde `backend/`, la sube a GHCR y despliega el stack con Helm en preprod.
- **Deploy to Production** (`.github/workflows/deploy-prod-on-release.yaml`): al publicar un release (o manual con tag) re-etiqueta la imagen `latest` con el tag del release y despliega el stack en prod.
- **Build Frontend & Deploy to Preprod** (`.github/workflows/build-frontend-deploy-preprod.yml`): en cada push a `main` construye la imagen del frontend desde `frontend/`, la sube a GHCR y despliega el chart del frontend en preprod.

**Secrets necesarios en el repo:**

- `KUBECONFIG_DATA`: contenido del kubeconfig (base64 o texto) para que Helm pueda desplegar en el cluster.
- `GITHUB_TOKEN`: lo proporciona GitHub; solo hace falta que el workflow tenga permisos para escribir en el registry (por defecto en push).

**Dockerfiles:**

- **Backend**: `backend/Dockerfile` — contexto de build `./backend`. Imagen usada por el stack (web + workers + scheduler).
- **Frontend**: `frontend/Dockerfile` — contexto de build `./frontend`. Imagen para la UI.
