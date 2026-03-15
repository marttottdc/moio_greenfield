# Fix crm_contacttype.tenant_id FK to use ON DELETE CASCADE so that updating or
# deleting a tenant does not violate the constraint (contact types are removed
# by DB cascade).

from django.db import migrations

CONSTRAINT_NAME = "crm_contacttype_tenant_id_862646cc_fk_portal_tenant_id"

DROP_FK = (
    f"ALTER TABLE crm_contacttype DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME};"
)
ADD_FK_CASCADE = (
    f"ALTER TABLE crm_contacttype ADD CONSTRAINT {CONSTRAINT_NAME} "
    "FOREIGN KEY (tenant_id) REFERENCES portal_tenant(id) ON DELETE CASCADE;"
)
ADD_FK_NO_CASCADE = (
    f"ALTER TABLE crm_contacttype ADD CONSTRAINT {CONSTRAINT_NAME} "
    "FOREIGN KEY (tenant_id) REFERENCES portal_tenant(id);"
)


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0003_contact_tenant_fk_on_delete_cascade"),
    ]

    operations = [
        migrations.RunSQL(
            sql=DROP_FK,
            reverse_sql=ADD_FK_NO_CASCADE,
        ),
        migrations.RunSQL(
            sql=ADD_FK_CASCADE,
            reverse_sql=DROP_FK,
        ),
    ]
