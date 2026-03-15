# Plan a largo plazo: Django-RLS + Endpoints

Objetivo: cerrar el plan de Django-RLS (tenancy + RLS + PgBouncer) y asegurar que todos los endpoints funcionen módulo por módulo, usando los resultados del barrido general y del stress lab como base.

---

## 1. Contexto

### Django-RLS (estado actual)
- **Middleware**: `MoioRLSContextMiddleware` (`tenancy/django_rls_middleware.py`) — transacción por request, `SET LOCAL app.current_tenant_slug` (y `rls.tenant_id`, `rls.user_id`), compatible con PgBouncer si se usa **session pooling** (o transaction con reset explícito).
- **Policy**: `tenancy/resolution.py` — public, external, tenant, optional por path.
- **Policies DB**: migraciones `tenancy.0002`–`0006`; tablas en `RLS_TABLES` con política por `app.current_tenant_slug` vía `portal_tenant`; platform (subdomain `'platform'`) visible para todos.
- **Docs**: `backend/docs/RLS_TENANCY.md`, `SHOPIFY_INSTALL_FLOW_RLS.md`, `MIGRATE_RLS_TROUBLESHOOTING.md`.

### Barrido general (resultados)
- **Matriz**: `backend/docs/ENDPOINT_AUDIT.md` — todos los mounts, policy, vista activa, CRM legacy vs modular.
- **Findings críticos**: dashboard usa demo_store (alta), datalab execute/query riesgo de aislamiento (alta), duplicación mixins/public_views (media), CRM legacy en communications/tickets/templates (media), users/integrations OAuth/flows/datalab/campaigns/docs/chatbot (media/baja).
- **Smoke tests**: lista mínima por módulo ya definida en el barrido.

### Stress lab
- 4 tenants, create/edit customers, contacts, activities, deals; 665 requests, 661 exitosos, 0 fallos de workload. Base sólida para CRM modular.

---

## 2. Principios del plan

- **Seguridad primero**: aislamiento tenant (RLS + PgBouncer correcto) y endpoints que no filtren mal (datalab, users).
- **Correctitud**: dashboard con datos reales; contratos claros (docs_api).
- **Consolidación**: una sola base de auth/mixins; preferir módulos sobre public_views donde sea sostenible.
- **Regresión**: suite de smoke tests por módulo y mantener stress lab como estándar.

---

## 3. Fases a largo plazo

### Fase A: Cierre Django-RLS e infra

**A.1 PgBouncer y RLS**
- Documentar en `backend/docs/RLS_TENANCY.md` (o nuevo `PgBouncer_RLS.md`):
  - **Recomendado**: `pool_mode = session` para RLS + variables de sesión (`SET LOCAL`); así cada request puede setear slug en su transacción sin contaminación.
  - Si se usa **transaction pooling**: exigir `server_reset_query = DISCARD ALL` (o `RESET ALL`) y `server_reset_query_always = 1`; documentar riesgo residual y que cualquier nueva variable de sesión debe estar cubierta por reset.
- Dejar explícito en docs que el middleware usa `SET LOCAL` (se limpia al final de la transacción) y que con session pooling no hay reutilización de conexión entre clientes.

**A.2 Tablas y políticas RLS**
- Revisar que todas las tablas tenant-scoped usadas por el API estén en `RLS_TABLES` y con política por slug (o platform). Añadir las que falten vía migración.
- Apps sin `TenantScopedModel` (ej. flows): si acceden a tablas con RLS, asegurar que siempre haya tenant en el request (middleware ya lo hace para rutas tenant); si tienen tablas propias con tenant_id, valorar añadir RLS o al menos filtro explícito por `request.tenant` en querysets.

**A.3 Rutas public/external sin tenant**
- Validar que ninguna view bajo `/api/platform/` o `/api/docs/` asuma `request.tenant` ni lea tablas RLS sin contexto explícito (ej. `tenant_rls_context(tenant)` cuando sea intencional). El barrido ya marcó este riesgo (Fase 2).

**Entregable**: Docs actualizados (PgBouncer + RLS), lista de tablas RLS verificada, y nota de que platform/docs no dependen de tenant por defecto.

---

### Fase B: Findings de severidad alta (endpoints que “funcionen” bien)

**B.1 Dashboard (F3-3)**
- Hoy: `DashboardSummaryView` en public_views usa `demo_store.dashboard()`.
- Objetivo: que la ruta activa use la implementación real (p. ej. `dashboard/views.py` con agregados reales).
- Opciones: (1) Cambiar `crm.api.dashboard.urls` para apuntar a `dashboard.views` en lugar de public_views; o (2) Reemplazar el cuerpo de `DashboardSummaryView` en public_views por la lógica de `dashboard/views.py` y deprecar el módulo dashboard si sobra.
- Incluir smoke: GET `api/v1/crm/dashboard/summary/` y contrastar con expectativa de negocio (métricas reales).

**B.2 Datalab (F5-2)**
- Validar que `execute/` y `crm/query` respeten tenant: todo acceso a datos dentro de `request.tenant` o de contexto RLS (middleware ya setea slug para rutas tenant).
- Revisar que no haya raw SQL o filtros manuales que omitan tenant_id/slug.
- Smoke: GET panels, GET datasets, POST execute con payload mínimo y JWT de tenant; opcional: dos tenants y comprobar que no se cruzan datos.

**Entregable**: Dashboard sirviendo datos reales; datalab con revisión documentada y smoke de aislamiento.

---

### Fase C: Findings de severidad media (consistencia y mantenibilidad)

**C.1 Unificar base de auth/mixins (F2-1)**
- Consolidar `ProtectedAPIView`, `ContactAPIMixin`, `TicketAPIMixin` en `crm.api.mixins` y que `public_views` los importe desde ahí (o eliminar duplicados y que las vistas legacy hereden de mixins). Objetivo: un solo lugar para cambios de auth/tenant.

**C.2 CRM legacy: communications, tickets, templates (F3-1, F3-2, F3-4)**
- Decisión de producto: mantener legacy a corto plazo o migrar a módulos.
  - **Opción 1 (mínimo)**: Dejar URLs en public_views pero asegurar que usen los mixins unificados (C.1) y que los smoke del barrido pasen.
  - **Opción 2 (largo plazo)**: Apuntar `communications/`, `tickets/`, `templates/` a sus `*/views.py` modulares; paridad de comportamiento vía tests; deprecar vistas en public_views para esos tres.
- En ambos casos: smoke GET (y POST donde aplique) para cada uno, con tenant JWT.

**C.3 Users (F4-4)**
- Verificar en `UserViewSet` que list/retrieve/update estén scoped por tenant (o por permiso platform si es intencional). Documentar el criterio. Smoke: GET list con tenant JWT.

**C.4 Integrations OAuth (F4-5)**
- Revisar callbacks OAuth (p. ej. email) bajo `/api/v1/integrations/`: si deben ser sin tenant, añadir prefijo exacto a `_EXTERNAL_PREFIXES` en resolution y AllowAny en la view; si corren con tenant, dejar como está. Documentar cada ruta external.

**C.5 Flows (F5-1), campaigns (F5-3), docs_api (F5-4), chatbot (F5-5)**
- Flows: asegurar que scheduled tasks y cualquier path con JWT fijen tenant (middleware ya lo hace para rutas tenant).
- Campaigns: aceptar dualidad legacy/FSM; documentar qué endpoints son “legacy” y cuáles “FSM”; mismo contrato estable.
- Docs_api: abordar contract drift (endpoint detail vs OpenAPI) en backlog; smoke GET endpoints y GET endpoint/<id>.
- Chatbot: revisar que sesiones estén atadas a tenant+contact y no haya fuga cross-tenant; smoke GET sessions, GET status.

**Entregable**: Mixins unificados; CRM legacy con decisión documentada y smoke pasando; users/integrations/flows/campaigns/docs/chatbot con revisión y smoke mínimos.

---

### Fase D: Smoke tests y regresión

**D.1 Suite de smoke por módulo**
- Implementar (script o tests) los smoke mínimos del barrido, por ejemplo:
  - Health, auth (login, me), bootstrap, content
  - CRM: communications summary, tickets list, dashboard summary, templates list; contacts, customers, activities, deals (list/detail donde aplique)
  - Platform: bootstrap (con auth platform si aplica)
  - Tenant: bootstrap (JWT tenant)
  - Tenants: self-provision (según contrato)
  - Users, integrations (list), flows (list + detail), scripts, datalab (panels, datasets, execute), campaigns (list + detail), docs (endpoints, endpoint detail), desktop-agent (sessions, status), resources (whatsapp-templates, webhooks, agent_tools)
- Configuración: base URL, credenciales (JWT tenant, opcional platform). Salida: OK/FAIL por endpoint o grupo.

**D.2 Integración en CI / pre-release**
- Ejecutar smoke suite en CI (o antes de release) además del stress lab. Objetivo: “todos los endpoints funcionan” módulo por módulo sin tener que probar a mano.

**Entregable**: Suite de smoke ejecutable y (opcional) integrada en pipeline; documento breve de cómo correrla.

---

### Fase E: Opcional — Migración tenancy (portal → tenancy)

- Si “terminar el plan Django-RLS” incluye la migración de portal a tenancy (`docs/tenancy_migration_plan.md`), seguir ese plan en orden (Fase 1 tenancy → Fase 4 context_utils/entitlements → Fase 2 Tenant a tenancy → Fase 3 integrations → Fase 5 limpieza).
- La migración no cambia el modelo RLS por slug; solo mueve modelos e imports. Coordinar con Fases A–D para no duplicar esfuerzo (p. ej. no tocar los mismos archivos a la vez).

---

## 4. Orden sugerido (largo plazo)

| Orden | Fase | Objetivo |
|-------|------|----------|
| 1 | A | RLS + PgBouncer documentado; tablas RLS verificadas; platform/docs sin dependencia incorrecta de tenant. |
| 2 | B | Dashboard real; datalab con aislamiento tenant verificado. |
| 3 | C.1 | Unificar mixins/public_views. |
| 4 | C.2–C.5 | Revisar users, integrations, flows, campaigns, docs, chatbot; decisión CRM legacy; smoke pasando. |
| 5 | D | Suite de smoke por módulo y uso en CI/pre-release. |
| 6 | E (opcional) | Migración tenancy si aplica. |

---

## 5. Criterio de “terminado”

- **Django-RLS**: Documentación PgBouncer+RLS clara; políticas RLS alineadas con tablas usadas por el API; rutas public/external sin asumir tenant.
- **Endpoints**: Findings alta resueltos (dashboard, datalab); media abordados (mixins, legacy, users, integrations, flows, campaigns, docs, chatbot); smoke suite pasando para todos los módulos del barrido.
- **Largo plazo**: Un solo criterio de auth/mixins; regresión automatizada (smoke + stress lab) para que cualquier cambio no rompa “que todos funcionen” módulo por módulo.

---

## 6. Referencias

- `backend/docs/ENDPOINT_AUDIT.md` — matriz de rutas, findings, smoke mínimos.
- `backend/docs/RLS_TENANCY.md` — RLS por slug, middleware, platform.
- `backend/tenancy/resolution.py` — policy por path.
- `backend/tenancy/django_rls_middleware.py` — MoioRLSContextMiddleware, SET LOCAL.
- `docs/tenancy_migration_plan.md` — portal → tenancy (opcional).
