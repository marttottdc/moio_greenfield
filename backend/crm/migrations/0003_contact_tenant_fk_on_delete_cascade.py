# Fix crm_contact.tenant_id FK to use ON DELETE CASCADE so that deleting
# a tenant does not violate the constraint (contacts are removed by DB cascade).

from django.db import migrations

CONSTRAINT_NAME = "crm_contact_tenant_id_79926372_fk_portal_tenant_id"

DROP_FK = (
    f"ALTER TABLE crm_contact DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME};"
)
ADD_FK_CASCADE = (
    f"ALTER TABLE crm_contact ADD CONSTRAINT {CONSTRAINT_NAME} "
    "FOREIGN KEY (tenant_id) REFERENCES portal_tenant(id) ON DELETE CASCADE;"
)
ADD_FK_NO_CASCADE = (
    f"ALTER TABLE crm_contact ADD CONSTRAINT {CONSTRAINT_NAME} "
    "FOREIGN KEY (tenant_id) REFERENCES portal_tenant(id);"
)


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_initial"),
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
