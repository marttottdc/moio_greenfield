# Test Tenant

Tenant y usuario para tests (API y frontend).

## Credenciales

| Campo | Valor |
|-------|-------|
| **Email** | `test@moio.ai` |
| **Password** | `test123` |
| **Subdomain** | `test` |
| **Organization** | Test Tenant |

## Backend

- **Base URL**: `http://127.0.0.1:8093`
- **Login**: `POST /api/v1/auth/login/`

## Creación (self-provision)

- **Con Redis + Celery:** Async (202 + poll). La tarea corre en el worker.
- **Sin Redis (`memory://`) o `?sync=1`:** Síncrono (201). Respuesta inmediata con tokens.

**Importante:** El subdomain debe cumplir RFC 1034/1035: solo letras minúsculas, números y guiones. No usar guiones bajos (`_`); por ejemplo usar `test2` en lugar de `test_2`.

### 1. Iniciar provisioning

```bash
curl -X POST http://127.0.0.1:8093/api/v1/tenants/self-provision/ \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Test Tenant",
    "subdomain": "test",
    "domain": "127.0.0.1",
    "email": "test@moio.ai",
    "username": "test@moio.ai",
    "password": "test123",
    "first_name": "Test",
    "last_name": "Admin"
  }'
```

Respuesta (202): `task_id`, `poll_url`.

### 2. Poll hasta completar

```bash
# Sustituir TASK_ID por el de la respuesta
curl http://127.0.0.1:8093/api/v1/tenants/provision-status/TASK_ID/
```

Cuando `status` sea `success`, la respuesta incluye `access_token`, `refresh_token`, `user`.

**Requisitos:** Celery worker corriendo (`celery -A moio_platform.celery_app worker -l info`).

## Uso

### API (tests automatizados / AI)

```bash
# Login
TOKEN=$(curl -s -X POST http://127.0.0.1:8093/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@moio.ai","password":"test123"}' \
  | jq -r '.access')

# Llamar API autenticada
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8093/api/v1/users/
```

### Frontend

- URL: `http://test.127.0.0.1:8093` o `http://127.0.0.1:8093` (según configuración de tenant resolution)
- Login con `test@moio.ai` / `test123`

## Requisitos previos

1. Backend corriendo en `http://127.0.0.1:8093`
2. Migraciones aplicadas (`migrate_schemas --shared` y `migrate_schemas`)
3. El subdomain `test` no debe existir (si ya existe, usar otro o borrar el tenant)

## Eliminar tenant

El comando de django-tenants `delete_tenant` tiene bugs. Usar el comando propio:

```bash
python manage.py remove_tenant -s SCHEMA_NAME --noinput
```

Ejemplo: `python manage.py remove_tenant -s test_2 --noinput`
