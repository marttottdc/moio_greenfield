"""
Backfill tenant_uuid on tenant-scoped tables where it is NULL.
Use after loading data from dump so RLS shows all rows.

  python manage.py backfill_tenant_uuid
"""
from django.core.management.base import BaseCommand
from django.db import connection


# Tenant-scoped tables with tenant_uuid; use actual db_table names from models
TABLES = [
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


class Command(BaseCommand):
    help = "Set tenant_uuid from portal_tenant.tenant_code where tenant_uuid IS NULL and tenant_id IS NOT NULL."

    def handle(self, *args, **options):
        q = connection.ops.quote_name
        total = 0
        with connection.cursor() as cursor:
            # With RLS on (by tenant slug), UPDATE in a command has no app.current_tenant_slug. Disable RLS for this run.
            try:
                cursor.execute("SET LOCAL row_level_security = off")
            except Exception as e:
                self.stderr.write("Note: could not set row_level_security (%s); backfill may still work if RLS is off." % e)
            for table in TABLES:
                try:
                    tn = q(table)
                    cursor.execute(
                        "UPDATE %s SET tenant_uuid = (SELECT tenant_code FROM portal_tenant WHERE portal_tenant.id = %s.tenant_id) WHERE tenant_uuid IS NULL AND tenant_id IS NOT NULL"
                        % (tn, tn)
                    )
                    n = cursor.rowcount
                    if n:
                        total += n
                        self.stdout.write("%s: %s row(s)" % (table, n))
                except Exception as e:
                    self.stderr.write("Skip %s: %s" % (table, e))
        connection.commit()
        self.stdout.write(self.style.SUCCESS("Backfilled %s row(s) total." % total))
