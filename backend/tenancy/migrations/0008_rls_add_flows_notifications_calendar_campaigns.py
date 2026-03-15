# A.2: Add RLS to tenant-scoped tables not in original RLS_TABLES.
# Same policy as 0006: visible if tenant = current tenant (by slug) OR tenant is platform (subdomain 'platform').

from django.db import migrations

# Tables with tenant_id (FK to Tenant) that were missing from RLS_TABLES in 0002/0006.
RLS_TABLES_ADD = [
    # flows
    "flows_flow",
    "flows_flowschedule",
    "flows_flowsignaltrigger",
    "flows_flowversion",
    "flows_flowscript",
    "flows_flowscriptversion",
    "flows_flowscriptrun",
    "flows_flowscriptlog",
    "flows_scheduled_task",
    "flows_task_execution",
    "flows_agent_context",
    "flows_agent_turn",
    # notifications
    "notifications_user_notification_preference",
    # moio_calendar (tenant-scoped models)
    "moio_calendar_calendar",
    "moio_calendar_calendarevent",
    "moio_calendar_availabilityslot",
    "moio_calendar_sharedresource",
    "moio_calendar_resourcebooking",
    "moio_calendar_bookingtype",
    # campaigns
    "campaigns_campaigndatastaging",
]


def enable_rls_new_tables(apps, schema_editor):
    connection = schema_editor.connection
    q = connection.ops.quote_name
    my_tenant_condition = (
        "tenant_id = (SELECT id FROM portal_tenant WHERE "
        "TRIM(subdomain) = NULLIF(TRIM(current_setting('app.current_tenant_slug', true)), '') "
        "LIMIT 1)"
    )
    platform_condition = (
        "tenant_id IN (SELECT id FROM portal_tenant WHERE TRIM(subdomain) = 'platform')"
    )
    condition = "(%s) OR (%s)" % (my_tenant_condition, platform_condition)
    for table in RLS_TABLES_ADD:
        try:
            tn = q(table)
            policy_name = q("rls_tenant_slug")
            schema_editor.execute(f"ALTER TABLE {tn} ENABLE ROW LEVEL SECURITY")
            schema_editor.execute(f"ALTER TABLE {tn} FORCE ROW LEVEL SECURITY")
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
        ("tenancy", "0007_alter_tenant_plan_default"),
    ]

    operations = [
        migrations.RunPython(enable_rls_new_tables, noop_reverse),
    ]
