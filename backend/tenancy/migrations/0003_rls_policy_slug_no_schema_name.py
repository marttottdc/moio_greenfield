# Update RLS policy to use only subdomain/tenant_code (no schema_name).

from django.db import migrations

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


def update_policy_no_schema_name(apps, schema_editor):
    connection = schema_editor.connection
    q = connection.ops.quote_name
    condition = (
        "tenant_id = (SELECT id FROM portal_tenant "
        "WHERE COALESCE(TRIM(subdomain), tenant_code::text) = "
        "NULLIF(TRIM(current_setting('app.current_tenant_slug', true)), '') "
        "LIMIT 1)"
    )
    for table in RLS_TABLES:
        try:
            tn = q(table)
            policy_name = q("rls_tenant_slug")
            schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {tn}")
            schema_editor.execute(
                f"CREATE POLICY {policy_name} ON {tn} "
                f"USING ({condition}) WITH CHECK ({condition})"
            )
        except Exception:
            pass


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0002_rls_policy_tenant_slug"),
    ]

    operations = [
        migrations.RunPython(update_policy_no_schema_name, noop_reverse),
    ]
