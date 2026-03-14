# RLS policies by tenant slug (subdomain or tenant_code)
# Middleware sets app.current_tenant_slug; policies filter by slug via portal_tenant.

from django.db import migrations

# Tenant-scoped tables (must have tenant_id FK). Same set as enable_rls/backfill_tenant_uuid.
RLS_TABLES = [
    "crm_activitycaptureentry", "crm_activityrecord", "crm_activitysuggestion", "crm_activitytype",
    "crm_branch", "crm_captureentryauditevent", "crm_captureentrylink", "crm_company",
    "crm_contact", "crm_contacttype", "crm_customer", "crm_customer_contact", "crm_deal",
    "ecommerce_order", "crm_face", "crm_facedetection", "crm_knowledgeitem",
    "crm_pipeline", "crm_pipelinestage", "crm_product", "crm_productvariant", "shipment",
    "shopify_customer", "shopify_order", "shopify_product", "shopify_sync_log",
    "crm_stock", "crm_tag", "crm_ticket", "webhook_config", "crm_webhookpayload",
    "datalab_accumulation_log", "datalab_analysis_model", "datalab_analyzer_run", "datalab_crm_view",
    "datalab_dataset", "datalab_dataset_version", "datalab_data_source", "datalab_file_asset",
    "datalab_file_set", "datalab_import_process", "datalab_import_run", "datalab_panel",
    "datalab_result_set", "datalab_semantic_derivation", "datalab_snapshot",
    "datalab_structural_unit", "datalab_widget",
    "campaigns_audience", "campaigns_audiencemembership", "campaigns_campaign", "campaigns_campaigndata",
    "integration_calendar_account", "integration_email_account", "integration_external_account",
    "integration_config",
    "agent_configuration", "assistant", "agent_session",
    "chatbot_emailaccount", "chatbot_emailmessage", "tenant_tool_configuration",
]


def enable_rls_by_slug(apps, schema_editor):
    connection = schema_editor.connection
    q = connection.ops.quote_name
    for table in RLS_TABLES:
        try:
            tn = q(table)
            policy_name = q("rls_tenant_slug")
            statements = [
                f"ALTER TABLE {tn} ENABLE ROW LEVEL SECURITY",
                f"ALTER TABLE {tn} FORCE ROW LEVEL SECURITY",
                f"DROP POLICY IF EXISTS {policy_name} ON {tn}",
            ]
            condition = (
                "tenant_id = (SELECT id FROM portal_tenant "
                "WHERE COALESCE(TRIM(subdomain), tenant_code::text) = "
                "NULLIF(TRIM(current_setting('app.current_tenant_slug', true)), '') "
                "LIMIT 1)"
            )
            statements.append(
                f"CREATE POLICY {policy_name} ON {tn} "
                f"USING ({condition}) WITH CHECK ({condition})"
            )
            for stmt in statements:
                schema_editor.execute(stmt)
        except Exception:
            # Table may not exist yet if migration order differs
            pass


def disable_rls(apps, schema_editor):
    connection = schema_editor.connection
    q = connection.ops.quote_name
    for table in RLS_TABLES:
        try:
            tn = q(table)
            schema_editor.execute(f"ALTER TABLE {tn} DISABLE ROW LEVEL SECURITY")
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0001_initial"),
        ("crm", "0002_initial"),  # run after main tenant-scoped tables exist
    ]

    operations = [
        migrations.RunPython(enable_rls_by_slug, disable_rls),
    ]
