# Auditoría: tareas Celery y respeto a RLS

## Objetivo

Revisar todas las tareas Celery que tocan tablas con RLS (tenant-scoped) y garantizar que:

- O bien reciben `tenant_id` / `tenant_slug` y ejecutan su lógica dentro de **`tenant_rls_context(tenant)`**,
- O bien están diseñadas para "todos los tenants" (p. ej. loop con contexto por tenant) y no desactivan RLS salvo en casos documentados.

**No** desactivar RLS por eficiencia; usar loop con cambio de tenant en cada iteración cuando se agregue sobre varios tenants.

---

## Resumen por módulo

### 1. central_hub (provisioning, KPIs)

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| create_tenant_for_provisioning | implícito (job) | Sí en seed | OK | — |
| seed_tenant_for_provisioning | job → tenant | Sí | OK | — |
| create_primary_user_for_provisioning | job → tenant | No | Revisar | Si toca tablas RLS (users por tenant), envolver en tenant_rls_context(tenant). |
| refresh_platform_admin_kpi_snapshots | tenant_slug opcional | No (usa run_full_sweep_rls_off) | Fallo | Cambiar a loop con tenant_rls_context; eliminar run_full_sweep_rls_off (plan ya acordado). |

### 2. central_hub.integrations.shopify

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| sync_shopify_products | tenant_id | Sí (schema_name) | OK | — |
| sync_shopify_customers | tenant_id | Sí | OK | — |
| sync_shopify_orders | tenant_id | Sí | OK | — |
| sync_all_shopify_data | tenant_id | Sí | OK | — |
| test_shopify_connection | tenant_id | Sí | OK | — |
| process_shopify_webhook | (por body/header) | En CRM: ver crm | Revisar | Ver sección CRM. |

### 3. chatbot

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| process_whatsapp_webhook_for_tenant | tenant_id, instance_id | Sí (schema_name) | OK | — |
| sync_single_tenant_tools_task | tenant_id | No | Revisar | Si sync_tenant_tools toca modelos con RLS, envolver en tenant_rls_context(tenant). |

### 4. moio_platform.core.events

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| route_event_task | tenant_id opcional | Sí (tras resolver tenant) | OK | — |

### 5. flows (execute_flow, scheduled, callbacks)

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| execute_flow | solo flow_id | **No** | **Fallo** | Añadir parámetro opcional tenant_id/tenant_slug; al inicio resolver Tenant y abrir `with tenant_rls_context(tenant):` antes de Flow.objects.get y resto. Actualizar router/views que encolan para pasar tenant. |
| preview_flow | flow_id, execution_id | No | Fallo | Idem: recibir tenant y setear contexto antes de tocar Flow/FlowExecution. |
| execute_sandbox_preview | idem | No | Fallo | Idem. |
| execute_scheduled_flow | schedule_id, flow_id, **tenant_id** | No | **Fallo** | Ya recibe tenant_id; envolver cuerpo en tenant_rls_context(tenant). |
| execute_scheduled_task | scheduled_task_id, **tenant_id** | No | Fallo | Resolver Tenant desde tenant_id (UUID string) y envolver en tenant_rls_context antes de ScheduledTask.objects.get. |
| run_scheduled_task_callback | execution_id | No | Fallo | TaskExecution tiene tenant; pasar tenant_id o leer execution.tenant y setear tenant_rls_context antes de get/update. |
| run_scheduled_task_error_callback | execution_id | No | Fallo | Idem. |
| execute_scheduled_task_immediate | (args del scheduled task) | Revisar | Idem si toca modelos RLS. |

Los executors (triggers, CRM, HTTP, outputs) se invocan desde el runtime del flow; si execute_flow/execute_scheduled_flow establecen contexto, heredan el tenant. **Prioridad: arreglar execute_flow y execute_scheduled_flow.**

### 6. flows.core.executors (CRM, HTTP, outputs)

Crean contact, ticket, etc. Llamados desde el runtime del flow. Dependen de que execute_flow / execute_scheduled_flow fijen tenant_rls_context. No cambiar executors mientras no esté arreglado el contexto en la tarea padre.

### 7. crm.tasks

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| classify_capture_entry | solo entry_id | No | **Fallo** | Añadir tenant_id (o tenant_slug); al inicio tenant_rls_context(tenant); actualizar capture/views: classify_capture_entry.delay(str(entry.id), tenant_id=entry.tenant_id). |
| apply_capture_entry | solo entry_id | No | Fallo | Idem; y en el chain apply_capture_entry.delay(entry_id, tenant_id=entry.tenant_id). |
| smart_address_fix | tenant_id | No | Revisar | Si toca órdenes/CRM con RLS, envolver en tenant_rls_context(tenant). |
| import_frontend_skus | tenant_id | No | Revisar | Idem. |
| process_received_order | order_number | No | Fallo | Necesita tenant en la llamada; setear contexto antes de EcommerceOrder.objects.get. |
| generic_webhook_handler | webhook_id | No | Fallo | WebhookConfig bajo RLS; necesitar tenant (o leer webhook sin RLS solo para tenant) y luego tenant_rls_context para el handler. |

Callers: `crm/api/capture/views.py` — pasar `entry.tenant_id` (o slug) en delay. `crm/views.py` — woocommerce_webhook_processor, generic_webhook_handler, create_smart_order, import_frontend_skus: asegurar que pasan tenant y las tareas usan tenant_rls_context.

### 8. campaigns.tasks

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| (execute_campaign, rebuild_index, etc.) | Revisar | Revisar | Revisar | Si leen/escriben Campaign u otros modelos con tenant_id, ejecutar dentro de tenant_rls_context(tenant). |

### 9. central_hub.integrations.v1 (email_ingest, calendar_ingest)

| Tarea | Recibe tenant | Usa tenant_rls_context | Estado | Acción |
|-------|----------------|-------------------------|--------|--------|
| email_ingest | Revisar | Revisar | Revisar | Comprobar si tocan modelos tenant-scoped y setear contexto. |
| calendar_ingest | Revisar | Revisar | Revisar | Idem. |

### 10. agent_console.tasks (run_agent_console_automation)

Revisar si toca datos por tenant y si usa tenant_rls_context.

### 11. moio_platform.lib.email (send_* tasks)

Revisar si envían correo en nombre de un tenant y si tocan modelos RLS; si es así, recibir tenant y usar tenant_rls_context.

---

## Patrón a aplicar

En cada tarea que toque datos por tenant:

```python
from tenancy.models import Tenant
from tenancy.tenant_support import tenant_rls_context

# Si la tarea recibe tenant_id (int) o tenant_slug (str):
tenant = Tenant.objects.get(id=tenant_id)  # o filter por subdomain/schema si slug
with tenant_rls_context(tenant.rls_slug):
    # todo el cuerpo que toque Flow, Contact, ActivityCaptureEntry, etc.
```

`tenant_rls_context` acepta también un objeto Tenant (vía `_resolve_tenant_ref`), por lo que se puede usar `tenant_rls_context(tenant)`.

---

## Orden de implementación sugerido

1. **flows**: execute_flow, execute_scheduled_flow, execute_scheduled_task, callbacks — añadir/uso de tenant_rls_context y, donde falte, parámetro tenant en la firma y en los .delay().
2. **crm**: classify_capture_entry, apply_capture_entry — añadir tenant_id a la tarea y a las llamadas desde capture/views; process_received_order, generic_webhook_handler — pasar tenant y contexto.
3. **central_hub**: refresh_platform_admin_kpi_snapshots — dejar de usar run_full_sweep_rls_off; usar solo loop con tenant_rls_context.
4. **Revisar y completar**: smart_address_fix, import_frontend_skus, campaigns, integrations/v1, agent_console, chatbot sync_single_tenant_tools_task, create_primary_user_for_provisioning, email tasks.

---

## Referencias

- `backend/tenancy/tenant_support.py`: `tenant_rls_context`, `_resolve_tenant_ref`.
- `backend/docs/RLS_TABLES_VERIFICATION.md`: tablas con RLS.
- `backend/docs/PLATFORM_ADMIN_KPIS.md`: KPIs y barrido por tenant.
