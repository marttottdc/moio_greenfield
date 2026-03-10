# Platform Configuration y limpieza de portal

## Completado

1. **PortalConfiguration → PlatformConfiguration** + Platform Admin
2. **Eliminados** (DB reset, sin migración):
   - Document, Instruction
   - AppConfig, AppMenu
   - ComponentTemplate, ContentBlock
   - TargetZone, ConversationHandler (enums)

## Pendiente

1. **Eliminar TenantConfiguration** y separar:
   - Propiedades propias del tenant (organización)
   - Configuraciones por integración (IntegrationConfig)

## Fase 1: Renombrar a Platform Configuration

- `PortalConfiguration` → `PlatformConfiguration`
- `portal_configuration` → `platform_configuration` (db_table)
- Admin: "Platform Configuration" bajo sección "Platform Admin"
- `get_portal_configuration()` → `get_platform_configuration()` (mantener alias temporal)

## Fase 2: Nuevo modelo TenantProfile (propiedades del tenant)

Propiedades que pertenecen al tenant como organización:

| Campo | Origen | Destino |
|-------|--------|---------|
| organization_currency | TenantConfiguration | TenantProfile |
| organization_timezone | TenantConfiguration | TenantProfile |
| organization_date_format | TenantConfiguration | TenantProfile |
| organization_time_format | TenantConfiguration | TenantProfile |
| default_notification_list | TenantConfiguration | TenantProfile |
| whatsapp_name | TenantConfiguration | TenantProfile (unique, para webhooks) |

Relación: Tenant 1:1 TenantProfile

## Fase 3: Integraciones en IntegrationConfig

Todo lo que es config de integración ya está en el registry y va a IntegrationConfig:

- openai, whatsapp, smtp, mercadopago, google, dac, hiringroom, psigma, zetasoftware
- woocommerce, wordpress, shopify, bitsistemas
- assistants (incluye conversation_handler, chatbot_enabled, default_agent_id, etc.)

Agregar a registry "assistants": agent_allow_reopen_session, agent_reopen_threshold

## Fase 4: Migración de datos y eliminación

1. Crear TenantProfile por cada Tenant existente con datos de TenantConfiguration
2. Asegurar IntegrationConfig poblado (ya existe _sync_to_integration_configs)
3. Crear facade `get_tenant_config(tenant)` que devuelva objeto compatible
4. Actualizar todos los usos (40+ referencias)
5. Eliminar TenantConfiguration
