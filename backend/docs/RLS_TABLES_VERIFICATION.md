# A.2 Verificación: tablas RLS completas

Lista de tablas con `tenant_id` (o FK a Tenant) y si tienen RLS aplicado (están en `RLS_TABLES` en migraciones tenancy).

## Tablas ya en RLS_TABLES (0002 / 0006)

- **CRM**: crm_activitycaptureentry, crm_activityrecord, crm_activitysuggestion, crm_activitytype, crm_branch, crm_captureentryauditevent, crm_captureentrylink, crm_company, crm_contact, crm_contacttype, crm_customer, crm_customer_contact, crm_deal, crm_face, crm_facedetection, crm_knowledgeitem, crm_pipeline, crm_pipelinestage, crm_product, crm_productvariant, crm_stock, crm_tag, crm_ticket, crm_webhookpayload, shipment, ecommerce_order, webhook_config
- **Datalab**: datalab_accumulation_log, datalab_analysis_model, datalab_analyzer_run, datalab_crm_view, datalab_dataset, datalab_dataset_version, datalab_data_source, datalab_file_asset, datalab_file_set, datalab_import_process, datalab_import_run, datalab_panel, datalab_result_set, datalab_semantic_derivation, datalab_snapshot, datalab_structural_unit, datalab_widget
- **Campaigns**: campaigns_audience, campaigns_audiencemembership, campaigns_campaign, campaigns_campaigndata
- **Integrations**: integration_calendar_account, integration_email_account, integration_external_account, integration_config
- **Chatbot / agent**: agent_configuration, assistant, agent_session, chatbot_emailaccount, chatbot_emailmessage, tenant_tool_configuration
- **Shopify**: shopify_customer, shopify_order, shopify_product, shopify_sync_log

## Tablas añadidas en migración 0008 (tenant-scoped sin RLS previo)

- **Flows**: flows_flow, flows_flowschedule, flows_flowsignaltrigger, flows_flowversion, flows_flowscript, flows_flowscriptversion, flows_flowscriptrun, flows_flowscriptlog, flows_scheduled_task, flows_task_execution, flows_agent_context, flows_agent_turn
- **Notifications**: notifications_user_notification_preference
- **Moio Calendar**: moio_calendar_calendar, moio_calendar_calendarevent, moio_calendar_availabilityslot, moio_calendar_sharedresource, moio_calendar_resourcebooking, moio_calendar_bookingtype (CalendarPermission y EventAttendee no tienen tenant_id; se accede vía calendar/event)
- **Campaigns**: campaigns_campaigndatastaging

## Excluidas o especiales

- **flows_event_log**: tiene `tenant_id` como UUID; la política estándar usa `(SELECT id FROM portal_tenant ...)` (integer). Dejar fuera hasta definir política por tenant_code/UUID si se requiere.
- **flows_event_definition**: sin tenant_id en el modelo; no aplicar RLS por tenant.
- **Tablas sin tenant (globales)**: portal_tenant, portal_tenant_domain, platform_*, shopify_oauth_state, shopify_shop_installation, shopify_shop_link, tenancy_* de definiciones/API keys (según diseño).

## Cómo añadir una tabla nueva

1. Asegurar que el modelo tiene `tenant_id` (FK a Tenant) o equivalente.
2. Crear una migración en `tenancy` que:
   - Añada la tabla a una lista `RLS_TABLES_ADD` (o editar la migración 0008 si aún no está aplicada).
   - Ejecute `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, y `CREATE POLICY rls_tenant_slug` con la misma condición que en 0006 (tenant actual o subdomain = 'platform').
