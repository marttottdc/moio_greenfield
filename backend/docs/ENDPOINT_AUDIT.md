# Barrido General de Endpoints – Auditoría Estática

Generado como parte del plan de validación módulo por módulo del API principal.

---

## Fase 1: Matriz Global de Rutas

Fuente: `moio_platform/urls.py` → includes. Policy: `tenancy/resolution.py` (`_PUBLIC_EXACT_PATHS`, `_PUBLIC_PREFIXES`, `_EXTERNAL_PREFIXES`, `_TENANT_REQUIRED_PREFIXES`, `_OPTIONAL_PREFIXES`).

### Rutas directas (sin include)

| Path | View / Handler | Policy | Auth esperada |
|------|----------------|--------|----------------|
| `webhooks/whatsapp/` | `whatsapp_webhook_receiver` | external | AllowAny / webhook |
| `webhooks/instagram/` | `instagram_webhook_receiver` | external | AllowAny |
| `webhooks/messenger/` | `messenger_webhook_receiver` | external | AllowAny |
| `webhooks/<str:webhook_id>/` | `generic_webhook_receiver` | external | AllowAny |
| `health`, `health/` | `probe_health` | (no en resolution; infra) | None |
| `api/v1/auth/login` | `AuthViewSet.login` | public | AllowAny |
| `api/v1/auth/refresh` | `AuthViewSet.refresh` | public | AllowAny |
| `api/v1/auth/me` | `AuthViewSet.me` | optional | IsAuthenticated |
| `api/v1/auth/logout` | `AuthViewSet.logout` | optional | IsAuthenticated |
| `api/v1/health/` | `health_check` | public | None |
| `api/v1/meta/endpoints/` | `meta_endpoints` | public | None |
| `api/v1/bootstrap/` | `BootstrapView` | tenant | IsAuthenticated + tenant |
| `api/v1/content/navigation/` | `NavigationView` | tenant | IsAuthenticated + tenant |
| `api/v1/test/` | `test_api` | public | AllowAny |
| `api/schema/` | `SpectacularAPIView` | public | None |

### Includes por módulo

| Mount | Include module | Policy | View source (activo) |
|-------|----------------|--------|----------------------|
| `api/v1/auth/` | `crm.api.auth.urls` | optional | `crm.api.auth.views.AuthViewSet` (router) |
| `api/platform/` | `central_hub.api.platform.urls` | public | `central_hub.api.platform.views` + `platform_bootstrap` |
| `api/tenant/` | `central_hub.api.tenant.urls` | tenant | `central_hub.api.tenant.views` |
| `api/v1/tenants/` | `central_hub.api.tenants.urls` | external | `central_hub.api.provisioning` (SelfProvision, ProvisionStatus) |
| `api/v1/users/` | `central_hub.api.users.urls` | tenant | `central_hub.api.users.views.UserViewSet` (router) |
| `api/v1/settings/` | `crm.api.settings.urls` | tenant | `crm.api.settings.views` (ViewSets + explicit views) |
| `api/v1/integrations/` | `central_hub.integrations.urls` | tenant (con excepciones external en resolution) | `central_hub.integrations.views` + v1 + shopify |
| `api/v1/crm/` | `crm.api.public_urls` → `crm.api.urls` | tenant | Ver subtabla CRM |
| `api/v1/activities/` | `crm.api.activities.urls` | tenant | `crm.api.activities.views` (modular) |
| `api/v1/capture/` | `crm.api.capture.urls` | tenant | `crm.api.capture.views` (modular) |
| `api/v1/timeline/` | `crm.api.timeline.urls` | tenant | `crm.api.timeline.views` (modular) |
| `api/v1/resources/` | `resources.api.urls` | tenant | `resources.api.views` + `crm.api.settings.views.WebhookConfigViewSet` |
| `api/v1/campaigns/` | `campaigns.api.urls` | tenant | `campaigns.api.views` (CRUD, config, execution, flow, stream) |
| `api/v1/flows/` | `flows.api_urls` | tenant | `flows.views` + schedule/event/scheduled_tasks views |
| `api/v1/scripts/` | `flows.api_script_urls` | tenant | `flows.api_script_views` |
| `api/v1/desktop-agent/` | `chatbot.api.urls` | tenant | `chatbot.api.desktop_agent` (function views) |
| `api/v1/datalab/` | `datalab.api.urls` | tenant | `datalab.api.views` + crm_views, panels, execute_views + analytics |
| `api/docs/` | `docs_api.urls` | public | `docs_api.views` |

### CRM sub-rutas (`api/v1/crm/`)

| Subpath | urls.py | View activa | Origen |
|---------|---------|-------------|--------|
| `contacts/` | `crm.api.contacts.urls` | ContactsSummaryView, ContactsView, ContactExportView, ContactDetailView, ContactPromoteView | **modular** `crm.api.contacts.views` |
| `communications/` | `crm.api.communications.urls` | CommunicationsSummaryView, ConversationsView, Detail, Messages, MarkRead, ChannelsView, WhatsappLogsView | **legacy** `crm.api.public_views` |
| `tickets/` | `crm.api.tickets.urls` | TicketListCreateView, TicketSummaryView, TicketDetailView, TicketCommentsView | **legacy** `crm.api.public_views` |
| `deals/` | `crm.api.deals.urls` | DealsView, DealDetailView, DealMoveStageView, DealCommentsView, Pipelines*, PipelineStage* | **modular** `crm.api.deals.views` |
| `templates/` | `crm.api.templates.urls` | TemplateListView | **legacy** `crm.api.public_views` |
| `dashboard/` | `crm.api.dashboard.urls` | DashboardSummaryView | **legacy** `crm.api.public_views` |
| `knowledge/` | `crm.api.knowledge.urls` | KnowledgeListView, KnowledgeDetailView | **modular** `crm.api.knowledge.views` |
| `customers/` | `crm.api.customers.urls` | CustomersView, CustomerDetailView | **modular** `crm.api.customers.views` |
| `tags/` | `crm.api.tags.urls` | TagsView, TagDetailView | **modular** `crm.api.tags.views` |
| `activities/` | (mount directo en moio_platform/urls) | — | No bajo crm/; es `api/v1/activities/` |
| `activity_types/` | `crm.api.activity_types.urls` | ActivityTypesView, ActivityTypeDetailView | **modular** `crm.api.activity_types.views` |
| `products/` | `crm.api.products.urls` | ProductsView, ProductDetailView | **modular** `crm.api.products.views` |
| `contact_types/` | `crm.api.contact_types.urls` | ContactTypesView, ContactTypeDetailView | **modular** `crm.api.contact_types.views` |

Resumen CRM: **Legacy** (public_views): communications, tickets, dashboard, templates. **Modular**: contacts, deals, knowledge, customers, tags, activity_types, products, contact_types.

---

## Fase 2: Hotspots de Infraestructura

### resolution.py
- **Prefijos vs policy**: Coherente. `_TENANT_REQUIRED_PREFIXES` incluye `/api/v1/crm/`, `/api/v1/activities/`, `/api/v1/capture/`, etc. `_PUBLIC_PREFIXES`: `/api/docs/`, `/api/platform/`. `_EXTERNAL_PREFIXES`: webhooks, tenants, integraciones Shopify/WhatsApp específicas.
- **Riesgo**: Rutas bajo `/api/v1/integrations/` son tenant en bloque; las excepciones external son por prefijo exacto (shopify/oauth, webhook, embed/bootstrap, etc.). Cualquier nueva ruta external bajo integrations debe añadirse a `_EXTERNAL_PREFIXES` o quedará como tenant.
- **Doc**: Módulo `tenancy/resolution.py` tiene docstring con la política por grupo y recordatorio de añadir callbacks external a `_EXTERNAL_PREFIXES`.

### django_rls_middleware.py
- **Flujo**: Para policy distinta de public/external, abre `transaction.atomic()`, corre `_prepare_request_context` (DRF auth + bind_request_tenant o ensure_request_tenant_context), luego `_set_local_rls_context` (SET LOCAL rls.tenant_id, rls.user_id, app.current_tenant_slug). Respuesta se sirve dentro del mismo atomic.
- **Riesgo**: Rutas public/external no reciben transacción ni contexto RLS en middleware; si alguna view bajo platform o docs hace queries a tablas RLS, podría depender de contexto heredado o vacío. Revisar que ningún handler bajo `/api/platform/` o `/api/docs/` asuma tenant.
- **Verificado**: Búsqueda en `central_hub/api/platform` y `docs_api`: ninguna view usa `request.tenant` ni `current_tenant`. Platform/docs no asumen tenant.

### tenancy/authentication.py
- **UserApiKeyAuthentication**: Devuelve (user, api_key); api_key tiene `.tenant`. Tenant se resuelve después vía middleware usando `request.auth.tenant`.
- **TenantJWTAAuthentication**: Subclase JWTAuthentication; no setea tenant en el token. Tenant se resuelve por JWT (tenant_schema) o por user en middleware.
- **Riesgo**: No hay setters duplicados de tenant en auth; todo pasa por resolution + middleware.

### crm/api/mixins.py
- **ProtectedAPIView**: Base para la mayoría de vistas CRM; authentication_classes estándar (session, api key, JWT, Bearer); permission_classes IsAuthenticated.
- **ContactAPIMixin**, **TicketAPIMixin**: Definen `_ensure_tenant_schema` (no-op), `_isoformat`, helpers de paginación/queryset. Usados por vistas modular y por public_views (que además define sus propias copias de ProtectedAPIView y mixins en public_views.py).
- **Riesgo**: Duplicación de base/mixins entre mixins.py y public_views.py. Cambios en uno no se reflejan en el otro; cualquier fix de auth/tenant en mixins debe replicarse o unificar.

**Finding F2-1**: Duplicación de ProtectedAPIView/ContactAPIMixin/TicketAPIMixin en `public_views.py` respecto de `mixins.py`. Severidad: media. **Resuelto**: public_views importa ProtectedAPIView y TicketAPIMixin desde `crm.api.mixins`; eliminadas las clases duplicadas en public_views.

### Checklist Fase 2 (cerrada)
- [x] resolution.py: prefijos coherentes; documentado en docstring del módulo.
- [x] django_rls_middleware.py: flujo documentado; platform/docs verificados (no usan request.tenant).
- [x] tenancy/authentication.py: sin setters duplicados; documentado.
- [x] crm/api/mixins.py: F2-1 resuelto (mixins unificados, public_views importa desde mixins).

---

## Fase 3: Barrido CRM Módulo por Módulo

### 3.1 communications (legacy)
- **Rutas activas**: summary, conversations, conversations/<id>, conversations/<id>/messages, conversations/<id>/mark-read, channels, whatsapp-logs. Todas desde `public_views`.
- **Implementación real**: `backend/crm/api/public_views.py` (CommunicationsConversationsView, etc.). Existe `communications/views.py` modular pero no está enlazado en urls.
- **Duplicados**: Sí; módulo `communications/views.py` tiene vistas equivalentes no usadas.
- **Queryset tenant**: Sí, vía mixin y request.user.tenant.
- **Serialización**: Manual en gran parte; no DRF serializers unificados.
- **Finding F3-1**: communications activo 100% legacy; summary y whatsapp-logs solo en public_views. Severidad: media. Smoke: GET summary, GET conversations, GET whatsapp-logs con tenant JWT.

### 3.2 tickets (legacy)
- **Rutas activas**: list/create, summary, detail, comments. Todas desde `public_views`.
- **Implementación real**: `public_views.TicketListCreateView`, etc. `tickets/views.py` existe y no se usa.
- **Duplicados**: Sí; comportamiento puede diferir entre public_views y tickets/views.
- **Finding F3-2**: tickets igual que communications; riesgo de drift. Severidad: media. Smoke: GET list, POST create, GET summary, GET detail, GET comments.

### 3.3 dashboard (legacy)
- **Ruta activa**: summary. View: `public_views.DashboardSummaryView`.
- **Implementación real**: En public_views usa `demo_store.dashboard()`. Existe `dashboard/views.py` con lógica distinta (agregados reales).
- **Finding F3-3**: Dashboard activo devuelve demo store; dashboard/views.py tiene implementación “real”. Severidad: alta (stale/incorrecto para prod). Smoke: GET summary y contrastar respuesta con expectativa de negocio.

### 3.4 templates (legacy)
- **Ruta activa**: list. View: `public_views.TemplateListView`.
- **Implementación real**: public_views. Existe `templates/views.py` modular no enlazado.
- **Finding F3-4**: templates duplicado; urls apuntan a legacy. Severidad: media. Smoke: GET list con tenant.

### 3.5 contacts, customers, activities, deals (modular)
- **contacts**: urls → `contacts/views.py`. RLS y transacción ya aplicados. Sin duplicado activo.
- **customers**: urls → `customers/views.py`. Idem.
- **activities**: urls → `activities/views.py`. Idem.
- **deals**: urls → `deals/views.py`. Idem.
- **Finding F3-5**: Ninguno crítico. Smoke: ya cubiertos por stress lab (create/edit). Opcional: GET list por recurso.

### 3.6 knowledge, tags, products, contact_types, activity_types, capture, timeline, auth, settings (modular)
- Todas las rutas apuntan a sus respectivos `*/views.py` o ViewSets en settings. No usan public_views para estos submódulos.
- **auth**: AuthViewSet en `crm.api.auth.views`; login/refresh/me/logout + router. AllowAny en login/refresh; resto autenticado.
- **settings**: ViewSets y vistas explícitas; tenant-scoped. Reutilización de WebhookConfigViewSet en resources (mismo view, otro mount).
- **Finding F3-6**: resources/webhooks usa WebhookConfigViewSet de CRM settings; asegurar que tenant y permisos sean los esperados bajo `/api/v1/resources/`. Severidad: baja. Smoke: GET/POST webhooks bajo resources con tenant JWT.

---

## Fase 4: Core Platform y Central Hub

### platform (`/api/platform/`)
- **Policy**: public. No requiere tenant.
- **Views**: PlatformBootstrapView, PlatformConfigurationSaveView, PlatformTenants*, PlatformUsers*, etc. Uso típico: admin/back-office.
- **Auth**: Revisar en views: muchas vistas platform usan RLS context con `public_schema_name()` o tenant explícito para operaciones admin. No hay conflicto con middleware porque policy=public no inyecta tenant.
- **Finding F4-1**: Ninguno crítico. Smoke: GET platform/bootstrap con credenciales de platform admin si aplica.

### tenant (`/api/tenant/`)
- **Policy**: tenant. Requiere tenant.
- **Views**: TenantBootstrapView, TenantUsersSaveView, TenantWorkspacesSaveView, TenantPluginsView, etc.
- **Finding F4-2**: Ninguno. Smoke: GET tenant/bootstrap con JWT tenant.

### tenants (`/api/v1/tenants/`)
- **Policy**: external (self-provision, provision-status). No requiere tenant en request.
- **Finding F4-3**: Ninguno. Smoke: POST self-provision según contrato.

### users (`/api/v1/users/`)
- **Policy**: tenant. UserViewSet bajo router. Puede tener ramas platform-admin (listar todos los usuarios); si es así, la ruta sigue siendo tenant-required a nivel middleware; la view puede decidir por rol. Coherente si la view comprueba is_staff/platform.
- **Finding F4-4**: Verificar en UserViewSet que list/retrieve/update estén scoped por tenant o por permiso platform. Severidad: media. Smoke: GET list con tenant JWT; GET list con usuario platform si existe. **Verified**: get_queryset filters by request.user.tenant for non-platform users; platform admins can pass tenant_id query param to scope.

### integrations (`/api/v1/integrations/`)
- **Policy**: tenant en bloque; excepciones en resolution para shopify/oauth, webhook, embed/bootstrap, chat-widget-config, app-proxy, whatsapp/embedded-signup.
- **Orden de rutas**: v1 y shopify incluidos primero; luego slug genérico. Correcto para no capturar shopify como slug.
- **Finding F4-5**: OAuth callbacks (p. ej. email) bajo tenant prefix pueden requerir AllowAny en esa view concreta; si no están en _EXTERNAL_PREFIXES, el middleware pedirá tenant. Revisar EmailOAuthCallbackView y similares. Severidad: media.

---

## Fase 5: Integrations y Módulos de Superficie Amplia

### integrations (ya cubierto en F4)
- Resumen: tenant con excepciones external por prefijo. Riesgo: callbacks OAuth bajo path tenant.

### flows
- **Rutas**: list, definitions, executions, flow detail, save, validate, preview, versions, publish, schedules, events, scheduled_tasks, task_executions, script list/detail/execute. Superficie muy amplia.
- **Auth**: Varias vistas con IsAuthenticated; scheduled tasks con CsrfExemptSessionAuthentication, TenantJWTAAuthentication, ServiceJWTAuthentication.
- **Finding F5-1**: Mezcla de auth en scheduled tasks; asegurar que tenant esté siempre fijado cuando se use JWT. Severidad: media. Smoke: GET flows/, GET flow/<id>, POST flow/<id>/save (si aplica), GET executions.

### datalab
- **Rutas**: files, filesets, imports, resultsets, crm/views, crm/query, panels, widgets, import-processes, import-runs, data-sources, datasets, dataset-versions, execute/, analytics.
- **Riesgo**: execute/ y crm/query ejecutan lógica dinámica/SQL. Auth en AuthenticatedDataLabView.
- **Finding F5-2**: Validar que execute y crm/query respeten tenant (filtros, RLS). Severidad: alta. Smoke: GET panels, GET datasets, POST execute con payload mínimo y tenant JWT. **Verified**: ExecuteView and CRMQueryViewSet use `get_tenant(request)`; runner passes tenant to CRMView lookup and to SQL executor; sql_executor requires `tenant_id = {{tenant_id}}` in raw SQL. Tenant isolation confirmed.

### campaigns
- **Rutas**: CRUD campaigns, audiences, config (legacy), execution (legacy), flow-state/transitions (FSM), stream (SSE). Celery + SSE.
- **Finding F5-3**: Dos estilos de API (legacy vs FSM); riesgo de inconsistencia. Smoke: GET campaigns, GET campaign/<id>, POST launch o transition según diseño.

### docs_api
- **Rutas**: schema, navigation, guides, endpoints (list/detail), examples, search, ingestion/status, validate, template. Mayoría AllowAny.
- **Finding F5-4**: Contract drift (endpoint detail vs OpenAPI). Severidad: media (ya reportado en issues previos). Smoke: GET endpoints, GET endpoint/<operation_id>.

### chatbot (desktop-agent)
- **Rutas**: sessions, session history, close, status, runtime/resources, agents, set-agent. Function-based.
- **Finding F5-5**: Session access por tenant + contact; revisar que no haya fuga cross-tenant. Severidad: media. Smoke: GET sessions, GET status.

### resources
- **Rutas**: whatsapp-templates (ViewSet), webhooks (WebhookConfigViewSet de CRM), contacts/search, agent_tools.
- **Finding F5-6**: webhooks reutiliza CRM settings viewset; tenant y permisos coherentes. Severidad: baja. Smoke: GET whatsapp-templates, GET webhooks, GET agent_tools.

---

## Resumen de Findings y Severidad

| ID | Módulo / Área | Severidad | Descripción |
|----|----------------|----------|-------------|
| F2-1 | mixins vs public_views | media | Duplicación de base/mixins entre mixins.py y public_views.py. |
| F3-1 | communications | media | 100% legacy; summary/whatsapp-logs solo en public_views; módulo modular no enlazado. |
| F3-2 | tickets | media | 100% legacy; módulo modular no enlazado; riesgo de drift. |
| F3-3 | dashboard | alta | Activo usa demo_store; dashboard/views.py tiene lógica real no usada. |
| F3-4 | templates | media | Legacy activo; módulo modular no enlazado. |
| F3-6 | resources/webhooks | baja | WebhookConfigViewSet compartido; validar tenant/permisos bajo resources. |
| F4-4 | users | media | Verificar scope tenant vs platform en UserViewSet. |
| F4-5 | integrations | media | Callbacks OAuth (p. ej. email) bajo tenant prefix; revisar AllowAny y _EXTERNAL_PREFIXES. |
| F5-1 | flows | media | Auth mixta en scheduled tasks; asegurar tenant. |
| F5-2 | datalab | alta | execute y crm/query; validar aislamiento tenant. |
| F5-3 | campaigns | media | Legacy + FSM; consistencia. |
| F5-4 | docs_api | media | Contract drift endpoint detail. |
| F5-5 | chatbot | media | Session/tenant; revisar fuga cross-tenant. |

---

## Smoke Tests Mínimos Recomendados (cola posterior)

1. **CRM legacy**: GET crm/communications/summary, GET crm/tickets/, GET crm/dashboard/summary, GET crm/templates/ (con tenant JWT).
2. **CRM modular**: GET/POST contacts, customers, activities, deals (ya cubiertos por stress lab).
3. **Platform**: GET api/platform/bootstrap (con auth platform si aplica).
4. **Tenant**: GET api/tenant/bootstrap (con tenant JWT).
5. **Tenants**: POST api/v1/tenants/self-provision (según contrato).
6. **Users**: GET api/v1/users/ (tenant JWT).
7. **Integrations**: GET api/v1/integrations/ (tenant JWT).
8. **Flows**: GET api/v1/flows/, GET api/v1/flows/<id>/.
9. **Datalab**: GET api/v1/datalab/panels/, GET api/v1/datalab/datasets/.
10. **Campaigns**: GET api/v1/campaigns/campaigns/.
11. **Docs**: GET api/docs/endpoints/, GET api/docs/endpoints/<operation_id>/.
12. **Desktop-agent**: GET api/v1/desktop-agent/sessions/, GET api/v1/desktop-agent/status/.
13. **Resources**: GET api/v1/resources/whatsapp-templates/, GET api/v1/resources/webhooks/.

---

*Fin del barrido estático. Próximo paso: ejecutar smoke tests mínimos y corregir findings por prioridad (alta: dashboard, datalab; media: restante).*

## Suite de smoke implementada

Ejecutable en `moio_platform/tests/test_smoke_endpoints.py`. Cubre: health, meta, bootstrap, content, users, settings, integrations, crm (contacts, communications, tickets, dashboard, templates, customers, deals), activities, capture, timeline, resources, campaigns, flows, scripts, datalab (panels, datasets), desktop-agent (sessions, status), docs (endpoints), tenant bootstrap. Requiere entorno con dependencias instaladas. Ejecutar:

```bash
cd backend && python manage.py test moio_platform.tests.test_smoke_endpoints -v 2
# o
pytest moio_platform/tests/test_smoke_endpoints.py -v
```
