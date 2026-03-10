# Protocolo de testing de API (startup)

Protocolo completo para validar el flujo de arranque de la plataforma con los tenants `test` y `test_2`: startup, bootstrap, usuarios, contactos, cuentas (customers), deals y actividades.

## Requisitos previos

1. Backend en `http://127.0.0.1:8093`
2. Migraciones aplicadas
3. Tenants existentes: `test`, `test_2`

### Resolución de tenant

Django-tenants usa el **Host** para resolver el tenant. Las operaciones de CRM (contacts, deals, activities, customers) deben usar el host del tenant:

- **test**: `Host: test.127.0.0.1`
- **test_2**: `Host: test2.127.0.0.1` (sin guión bajo: RFC no permite `_` en hostnames)

Login y self-provision usan `127.0.0.1` (schema público). El resto de las llamadas autenticadas que tocan CRM deben usar el host del tenant.

---

## Fase 1: Tenant `test`

### 1.1 Health check

```bash
curl -s http://127.0.0.1:8093/api/v1/health/ | jq
```

Esperado: `200`, payload con estado ok.

### 1.2 Login

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8093/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@moio.ai","password":"test123"}' \
  | jq -r '.access')
echo "Token: ${TOKEN:0:50}..."
```

Credenciales: `test@moio.ai` / `test123` (tenant_admin)

### 1.3 Bootstrap

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  http://127.0.0.1:8093/api/v1/bootstrap/ | jq
```

Verificar:
- `user.id`, `user.email`, `user.role` (tenant_admin)
- `profile.display_name`, `profile.locale`
- `tenant.id`, `tenant.nombre`, `tenant.plan`
- `entitlements.features`, `entitlements.limits`
- `capabilities.allowed` (lista de capacidades)

### 1.4 Crear usuarios

El tenant_admin puede crear usuarios. Crear un `member` y un `manager`:

**Member:**
```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "member@test.moio.ai",
    "username": "member@test.moio.ai",
    "first_name": "Member",
    "last_name": "User",
    "password": "member123",
    "role": "member"
  }' \
  http://127.0.0.1:8093/api/v1/users/ | jq
```

**Manager:**
```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "manager@test.moio.ai",
    "username": "manager@test.moio.ai",
    "first_name": "Manager",
    "last_name": "User",
    "password": "manager123",
    "role": "manager"
  }' \
  http://127.0.0.1:8093/api/v1/users/ | jq
```

Verificar: `201`, `id`, `email`, `role`.

### 1.5 Crear contactos

```bash
# Contacto 1
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "fullname": "Juan Pérez",
    "email": "juan@example.com",
    "phone": "+59899123456",
    "company": "Acme SA"
  }' \
  http://127.0.0.1:8093/api/v1/crm/contacts/ | jq

# Contacto 2
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "fullname": "María García",
    "email": "maria@example.com",
    "phone": "+59898765432"
  }' \
  http://127.0.0.1:8093/api/v1/crm/contacts/ | jq
```

Listar contactos:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  "http://127.0.0.1:8093/api/v1/crm/contacts/?limit=10" | jq
```

### 1.6 Crear cuentas (customers)

```bash
# Cuenta empresa
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "legal_name": "Acme Corporation SA",
    "type": "company",
    "email": "info@acme.com",
    "phone": "+59829001234"
  }' \
  http://127.0.0.1:8093/api/v1/crm/customers/ | jq
```

Listar customers:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  "http://127.0.0.1:8093/api/v1/crm/customers/?limit=10" | jq
```

### 1.7 Crear pipeline por defecto (para deals)

Si el tenant no tiene pipeline, crear uno:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  http://127.0.0.1:8093/api/v1/crm/deals/pipelines/create-default/ | jq
```

Listar pipelines y stages:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  "http://127.0.0.1:8093/api/v1/crm/deals/pipelines/" | jq
```

### 1.8 Crear deals

Obtener `pipeline_id` y `stage_id` de la respuesta anterior (o del listado de deals que incluye pipelines).

```bash
# Deal sin pipeline/stage (válido)
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Deal Acme - Licencias",
    "description": "Venta de 50 licencias",
    "value": 5000,
    "currency": "USD"
  }' \
  http://127.0.0.1:8093/api/v1/crm/deals/ | jq
```

O con contact y pipeline/stage (reemplazar IDs):
```bash
# Ejemplo con contact_id y stage_id
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Deal María",
    "contact": "CONTACT_UUID",
    "pipeline": "PIPELINE_UUID",
    "stage": "STAGE_UUID",
    "value": 2500,
    "currency": "USD"
  }' \
  http://127.0.0.1:8093/api/v1/crm/deals/ | jq
```

Listar deals:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  "http://127.0.0.1:8093/api/v1/crm/deals/" | jq
```

### 1.9 Crear actividades

```bash
# Actividad tipo nota
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Llamada de seguimiento",
    "kind": "note",
    "content": {"body": "Cliente interesado, enviar propuesta"},
    "status": "completed",
    "visibility": "public"
  }' \
  http://127.0.0.1:8093/api/v1/activities/ | jq
```

Con `contact_id` (UUID del contacto creado antes):
```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Reunión con Juan",
    "kind": "task",
    "content": {"body": "Revisar contrato"},
    "contact_id": "CONTACT_UUID",
    "status": "scheduled",
    "scheduled_at": "2025-03-15T10:00:00Z"
  }' \
  http://127.0.0.1:8093/api/v1/activities/ | jq
```

Listar actividades:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Host: test.127.0.0.1" \
  "http://127.0.0.1:8093/api/v1/activities/?limit=10" | jq
```

---

## Fase 2: Tenant `test_2`

Repetir los mismos pasos usando el tenant `test_2`. Credenciales dependen de cómo se creó el tenant (self-provision). Ejemplo típico: `test2@moio.ai` / `test123`.

### 2.1 Login (test_2)

```bash
TOKEN2=$(curl -s -X POST http://127.0.0.1:8093/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test2@moio.ai","password":"test123"}' \
  | jq -r '.access')
```

Si `test_2` se creó con otras credenciales, ajustar el payload.

### 2.2 Subdomain válido (RFC)

**Importante:** Al crear tenants vía self-provision, usar subdomains RFC‑compliant: solo letras minúsculas, números y guiones. **No usar guiones bajos** (`test_2` es inválido). Usar `test2` en lugar de `test_2`.

### 2.3 Host para test_2

En todas las llamadas de CRM reemplazar:
- `Host: test.127.0.0.1` → `Host: test_2.127.0.0.1`
- `$TOKEN` → `$TOKEN2`

Y usar emails únicos por tenant para usuarios/contactos, p.ej.:
- `member2@test2.moio.ai`, `manager2@test2.moio.ai`
- Contactos con emails distintos

---

## Checklist de validación

| Paso | Endpoint | Esperado |
|------|----------|----------|
| 1.1 | GET /api/v1/health/ | 200, ok |
| 1.2 | POST /api/v1/auth/login/ | 200, access + refresh |
| 1.3 | GET /api/v1/bootstrap/ | 200, user+profile+tenant+entitlements+capabilities |
| 1.4 | POST /api/v1/users/ | 201, user con role |
| 1.5 | POST /api/v1/crm/contacts/ | 201, contact |
| 1.6 | POST /api/v1/crm/customers/ | 201, customer |
| 1.7 | POST .../pipelines/create-default/ | 201 o 400 (ya existe) |
| 1.8 | POST /api/v1/crm/deals/ | 201, deal |
| 1.9 | POST /api/v1/activities/ | 201, activity |

---

## Errores frecuentes

1. **401 Unauthorized**: Token inválido o expirado. Volver a hacer login.
2. **403 Forbidden**: Usuario sin permiso (p.ej. member no puede crear usuarios), o **falta el header Host** del tenant. Todas las llamadas de CRM/usuarios deben incluir `-H "Host: test.127.0.0.1"` (o `test2.127.0.0.1` para test_2).
3. **404 / relation does not exist**: Host incorrecto — CRM requiere el host del tenant (`test.127.0.0.1`).
4. **400 subdomain already taken**: El tenant ya existe. Usar credenciales existentes o otro subdomain.

5. **404 con Host test_2.127.0.0.1**: Los guiones bajos no son válidos en hostnames (RFC). Añadir dominio alternativo `test2.127.0.0.1` para el tenant test_2:
   ```bash
   python manage.py shell -c "
   from tenancy.models import Tenant, TenantDomain
   t = Tenant.objects.get(schema_name='test_2')
   TenantDomain.objects.get_or_create(domain='test2.127.0.0.1', defaults={'tenant': t})
   "
   ```

---

## Script automatizado

Ver `backend/scripts/run_api_startup_protocol.sh` para ejecutar el protocolo de forma automática.
