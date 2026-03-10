# Plan: nueva app `tenancy` y migración desde `portal`

Objetivo: crear la app `tenancy` con la responsabilidad de multi-tenancy e integraciones, e ir migrando desde `portal`. El nombre "tenancy" describe mejor esta capa que "portal".

**Contexto importante**: Se puede hacer un database reset sin problemas. No hace falta migrar datos ni preservar tablas existentes; podemos definir las tablas nuevas en tenancy desde cero y arrancar limpio.

---

## Estado actual

| Componente | Ubicación | Observaciones |
|------------|-----------|---------------|
| Tenant, TenantDomain | portal | Modelos base de django-tenants |
| TenantScopedModel, TenantManager | portal | Base para modelos por tenant |
| context_utils (current_tenant) | portal | ContextVar usado en toda la app |
| IntegrationConfig | portal.integrations | Config por tenant, multi-instancia |
| IntegrationDefinition | portal.integrations.registry | Dataclass en código (no DB) |
| TenantConfiguration | portal | Legacy, muchos campos hardcodeados |
| entitlements_defaults | portal | Features/limits por plan |
| MoioUser, UserProfile, etc. | portal | Usuarios y perfil |

**TENANT_MODEL** = `portal.Tenant`  
**TENANT_DOMAIN_MODEL** = `portal.TenantDomain`  
**portal** está en SHARED_APPS (porque Tenant vive en schema public).

---

## Fases del plan

### Fase 1: Crear app `tenancy` (sin mover Tenant)

**Objetivo**: App nueva con modelos adicionales, sin romper nada.

1. **Crear app `tenancy`**
   - `python manage.py startapp tenancy`
   - Añadir `tenancy` a SHARED_APPS (antes de portal, para depender de django_tenants)
   - `tenancy` depende de `portal` (importa `Tenant` para FKs)

2. **Modelos nuevos en tenancy** (inspirados en waste/webchat_django/tenancy)
   - `IntegrationDefinition` (modelo DB): key, name, category, base_url, auth_type, auth_scope, assistant_docs_markdown, etc.
   - `TenantIntegration`: binding tenant↔integration (tenant_auth_config, assistant_docs_override)
   - `UserIntegrationCredential` (opcional Fase 1): credenciales por usuario

3. **Módulo `integration_guidance.py`**
   - `build_tenant_integration_guidance_sync(tenant_schema, …)`: markdown para agentes
   - `list_tenant_integrations_for_agent_sync(tenant_schema, …)`: lista estructurada
   - Usar `schema_context("public")` para consultar en Postgres

4. **Comandos de management**
   - `tenancy bootstrap_tenant`: crear tenant + domain (como waste)
   - `tenancy list_tenants`: listar tenants

5. **Compatibilidad**
   - Portal sigue siendo fuente de verdad para Tenant, TenantDomain.
   - `IntegrationConfig` en portal se mantiene; los nuevos `TenantIntegration` y `IntegrationDefinition` coexisten.

**Riesgo**: Bajo. No tocamos modelos existentes.

---

### Fase 2: Migrar Tenant, TenantDomain, TenantScopedModel a tenancy

**Objetivo**: Tenant y dominios pasan a ser propiedad de tenancy.

1. **Mover modelos a tenancy**
   - Copiar `Tenant`, `TenantDomain`, `TenantScopedModel`, `TenantManager`, `ContentBlockManager` a `tenancy/models.py`.
   - Crear tablas nuevas `tenancy_tenant`, `tenancy_tenantdomain`. Con DB reset no preservamos datos.

2. **Actualizar referencias**
   - Cambiar `from portal.models import Tenant` → `from tenancy.models import Tenant` en todo el backend.
   - Portal deja de definir esos modelos.

3. **Settings**
   - `TENANT_MODEL = "tenancy.Tenant"`
   - `TENANT_DOMAIN_MODEL = "tenancy.TenantDomain"`

4. **Reset de DB**
   - `dropdb` + `createdb` + `migrate` para arrancar limpio. O borrar migraciones viejas y regenerar.
   - Sin datos legacy, no hay migración de datos ni hacks de `db_table`.

**Riesgo**: Bajo con DB reset. Sin reset sería medio.

---

### Fase 3: Migrar integraciones a tenancy

**Objetivo**: `IntegrationConfig` y registry pasan a tenancy.

1. **Mover `portal.integrations` a `tenancy.integrations`**
   - `IntegrationConfig` → tenancy
   - `IntegrationDefinition` (dataclass) → mantener en registry, o migrar a modelo `IntegrationDefinition` en DB
   - `INTEGRATION_REGISTRY` → tenancy.integrations.registry

2. **Actualizar `TenantConfiguration`**
   - Mantener la sincronización write-through a IntegrationConfig, pero el destino es tenancy.
   - O planificar deprecación de TenantConfiguration a favor de solo IntegrationConfig.

3. **Actualizar imports**
   - `from portal.integrations.models import IntegrationConfig` → `from tenancy.integrations.models import IntegrationConfig`
   - Ajustar URLs, vistas, admin.

**Riesgo**: Medio. Muchos imports y rutas afectados.

---

### Fase 4: Context utils y utilidades compartidas

**Objetivo**: Centralizar lógica de tenancy.

1. **Mover `context_utils` a tenancy**
   - `current_tenant`, `set_current_tenant` → `tenancy.context_utils`
   - `portal.middleware` y otros módulos usan `tenancy.context_utils`

2. **Mover `entitlements_defaults` a tenancy**
   - `get_default_features_for_plan`, `get_default_limits_for_plan`, etc.
   - Los signals de portal que crean TenantConfiguration/IntegrationConfig importan desde tenancy.

**Riesgo**: Bajo. Cambios de import principalmente.

---

### Fase 5 (opcional): Limpieza de portal

**Objetivo**: Dejar portal con responsabilidades claras.

- Portal se centra en: `MoioUser`, `UserProfile`, `AuthSession`, `UserApiKey`, `PortalConfiguration`, `ContentBlock`, `AppConfig`, `AppMenu`, UI, vistas, etc.
- Tenancy se centra en: Tenant, dominios, integraciones, membership (si se añade), guidance para agentes.

---

## Orden sugerido de ejecución

| Orden | Fase | Duración est. | Bloqueante |
|-------|------|---------------|------------|
| 1 | Fase 1: Crear tenancy + modelos nuevos + integration_guidance | 1–2 días | No |
| 2 | Fase 4: context_utils y entitlements a tenancy | 0.5 día | No |
| 3 | Fase 2: Migrar Tenant/TenantDomain a tenancy | 1 día con DB reset | Sí (migraciones) |
| 4 | Fase 3: Migrar integrations a tenancy | 2–3 días | Depende de Fase 2 |
| 5 | Fase 5: Limpieza | 0.5 día | No |

---

## Estructura objetivo de tenancy

```
tenancy/
├── __init__.py
├── apps.py
├── models.py              # Tenant, TenantDomain, TenantScopedModel, IntegrationDefinition, TenantIntegration, UserIntegrationCredential
├── context_utils.py       # current_tenant
├── integration_guidance.py # build_tenant_integration_guidance_sync, list_tenant_integrations_for_agent_sync
├── entitlements_defaults.py
├── management/
│   └── commands/
│       ├── bootstrap_tenant.py
│       └── list_tenants.py
├── integrations/          # (fase 3)
│   ├── models.py          # IntegrationConfig
│   ├── registry.py        # INTEGRATION_REGISTRY
│   ├── views.py
│   └── ...
└── migrations/
```

---

## Checklist por fase

### Fase 1
- [ ] Crear app tenancy
- [ ] Añadir a SHARED_APPS
- [ ] Modelo IntegrationDefinition (DB)
- [ ] Modelo TenantIntegration
- [ ] integration_guidance.py
- [ ] Comandos bootstrap_tenant, list_tenants
- [ ] Migraciones iniciales
- [ ] Tests básicos

### Fase 2
- [ ] Migrar Tenant, TenantDomain, TenantScopedModel
- [ ] Actualizar TENANT_MODEL, TENANT_DOMAIN_MODEL
- [ ] Reemplazar imports en todo el backend
- [ ] Regenerar migraciones o DB reset (dropdb + migrate)
- [ ] Validar en dev y staging

### Fase 3
- [ ] Mover portal.integrations a tenancy.integrations
- [ ] Actualizar TenantConfiguration._sync_to_integration_configs
- [ ] Actualizar imports
- [ ] Admin, URLs, vistas

### Fase 4
- [ ] Mover context_utils a tenancy
- [ ] Mover entitlements_defaults a tenancy
- [ ] Actualizar imports

---

## DB reset (fresh deploy)

Para base de datos nueva (local):
```bash
dropdb moio_greenfield_dev   # o el nombre de tu DB
createdb moio_greenfield_dev
cd backend && python manage.py migrate
python manage.py ensure_dev_user
```

Para base de datos remota (usar variables de .env.dev.local):
```bash
# Conectar a postgres y ejecutar:
# DROP DATABASE moio_greenfield_dev; CREATE DATABASE moio_greenfield_dev;
# Luego:
cd backend && python manage.py migrate
python manage.py ensure_dev_user
```

Con tenancy aplicado, `bootstrap_tenant` crea tenants:
```bash
python manage.py bootstrap_tenant --schema dev --name "Dev" --domain localhost --subdomain dev
python manage.py list_tenants --schema
```

## Estado actual (post-migración)

- **tenancy**: Tenant, TenantDomain, TenantScopedModel, IntegrationDefinition, TenantIntegration, context_utils, entitlements_defaults, integration_guidance
- **portal**: re-exporta Tenant/context_utils/entitlements para compatibilidad; MoioUser, TenantConfiguration, etc.
- **portal.integrations**: sigue en portal (IntegrationConfig usa tenancy.Tenant)

## Referencias

- waste/desktop-agent-console/webchat_django/tenancy (modelos e integration_guidance)
- backend/portal (estado actual)
