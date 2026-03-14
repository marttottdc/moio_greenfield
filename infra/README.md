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

- **Pushpin (opcional, por defecto on)**: proxy inverso para HTTP y WebSockets (como en moio_platform). Si `pushpin.enabled: true`, el Ingress envía tráfico `/api`, `/ws`, `/admin`, `/health` a **pushpin-service**, que reenvía al backend (Hypercorn/ASGI). Permite WebSockets y long-polling correctos. Con `pushpin.enabled: false` el Ingress apunta directo al backend. **Django no conecta a Pushpin**: es Pushpin quien abre conexión al backend; no hace falta instalar nada extra para el proxy. Para *server push* (publicar desde el backend a clientes WebSocket) opcionalmente se puede configurar GRIP (ver más abajo).
- **PgBouncer (opcional)**: si en values pones `pgbouncer.enabled: true`, el chart despliega un PgBouncer dentro del cluster que se conecta a tu Postgres externo; la app usa entonces `postgres://...@pgbouncer:6432/...`. Si `pgbouncer.enabled: false` (por defecto), usas `config.database_url` apuntando a un PgBouncer o Postgres externo.

## Frontend (UI)

- **Chart**: `frontend/deploy/chart/` (moio-frontend).
- Despliegue independiente del stack de backend (otra release Helm o mismo namespace con otro release).

## Despliegue

1. Crear namespace y secret de registro si aplica:
   ```bash
   kubectl create namespace moio-greenfield
   kubectl create secret docker-registry registry-4 --from-file=.dockerconfigjson=... -n moio-greenfield
   ```

2. **Secretos y config**: copiar `infra/environments/values-secrets.example.yaml` a `infra/environments/values-secrets.yaml` (o `preprod-secrets.yaml` / `prod-secrets.yaml`), completar y **no commitear**:
   - `config.database_url` → Postgres o PgBouncer (ej. `postgres://user:pass@host:6432/moio_greenfield`)
   - `config.redis_url` → Redis (ej. `redis://host:6379/0`)
   - `secrets.secret_key` → Django (ej. `openssl rand -base64 48`)

3. Instalar el stack backend + workers:
   ```bash
   helm upgrade --install moio-greenfield-stack ./infra/charts/moio-greenfield-stack \
     -f infra/environments/prod.yaml \
     -f infra/environments/values-secrets.yaml \
     -n moio-greenfield --create-namespace ...
   ```

4. Instalar el frontend (si aplica):
   ```bash
   helm upgrade --install moio-frontend ./frontend/deploy/chart -n moio-greenfield -f frontend/deploy/chart/values.yaml
   ```

## Entornos

- **preprod**: `infra/environments/preprod.yaml` (1 replica por componente, URLs preprod).
- **prod**: `infra/environments/prod.yaml` (réplicas tipo moio_platform: backend 2, worker-high 4, etc.).

Ajustar `ingress.host`, `ingress.tlsSecret` e `image.repository`/`image.tag` según tu registro y dominio.

### PgBouncer dentro del chart (opcional)

Para desplegar PgBouncer en el cluster (conexión a Postgres externo):

```yaml
# en values o en -f pgbouncer-values.yaml
pgbouncer:
  enabled: true
  replicas: 1
  backend:
    host: "tu-postgres-host"   # hostname o IP del Postgres
    port: 5432
    dbname: moio_greenfield
  auth:
    user: "postgres_user"
    password: "postgres_password"
```

La app usará `postgres://user:password@pgbouncer:6432/dbname` automáticamente. El Service `pgbouncer` queda en el mismo namespace.

### Django y Pushpin (qué instalar)

- **Conexión básica (proxy)**: **No hace falta instalar nada en Django.** Pushpin es un proxy inverso: el cliente habla con Pushpin y Pushpin abre la conexión a tu backend (Hypercorn en el puerto 8010). Django solo escucha; Pushpin se conecta a él. Con el chart actual (rutas `* → backend:80`) ya funciona HTTP y WebSocket cliente→servidor.
- **Opcional – server push (GRIP)**: Si quieres que el backend *envíe* mensajes a WebSockets (p. ej. `channel_layer.group_send()` que llegue a clientes vía Pushpin), hace falta que Django hable con la API de control de Pushpin (GRIP). En el repo ya están en `requirements.txt`: `django-grip` y `gripcontrol`. Para usarlos habría que configurar en `settings.py` algo como `GRIP_URL` apuntando al control de Pushpin (p. ej. `http://pushpin-service:5561`) y, si se usa, un channel layer que use GRIP. Sin eso, el channel layer actual (`channels_redis`) sigue funcionando entre workers; para broadcast a muchos clientes WebSocket con varias réplicas de backend, GRIP suele ser la opción.

## GitHub Actions CI

- **Build Backend & Deploy to Preprod** (`.github/workflows/build-backend-deploy-preprod.yml`): en cada push a `main` construye la imagen desde `backend/`, la sube a GHCR y despliega el stack con Helm en preprod.
- **Deploy to Production** (`.github/workflows/deploy-prod-on-release.yaml`): al publicar un release (o manual con tag) re-etiqueta la imagen `latest` con el tag del release y despliega el stack en prod.
- **Build Frontend & Deploy to Preprod** (`.github/workflows/build-frontend-deploy-preprod.yml`): en cada push a `main` construye la imagen del frontend desde `frontend/`, la sube a GHCR y despliega el chart del frontend en preprod.

**Secrets necesarios en el repo:**

- `KUBECONFIG_DATA`: kubeconfig para Helm/kubectl. Acepta **texto plano** o **base64** (se detecta solo). Recomendado base64 para evitar problemas con newlines: `kubectl config view --minify --raw | base64 -w 0` (macOS: sin `-w 0`). Pegar en Settings → Secrets → KUBECONFIG_DATA.
- `GITHUB_TOKEN`: lo proporciona GitHub; solo hace falta que el workflow tenga permisos para escribir en el registry (por defecto en push).

**Dockerfiles:**

- **Backend**: `backend/Dockerfile` — contexto de build `./backend`. Imagen usada por el stack (web + workers + scheduler).
- **Frontend**: `frontend/Dockerfile` — contexto de build `./frontend`. Imagen para la UI.
