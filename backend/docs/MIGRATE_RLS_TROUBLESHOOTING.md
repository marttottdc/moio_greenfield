# Migration troubleshooting (RLS / tenant_uuid)

## "relation \"campaigns_audience\" does not exist" (or similar) when applying `*_add_tenant_uuid_for_rls`

This usually means the migration table is recorded as applied for earlier migrations, but the actual app tables were never created (e.g. fresh or restored DB, or tables dropped).

**Fix: reset the app’s migration state and re-apply**

For the failing app (e.g. `campaigns`), fake back to zero then run all migrations:

```bash
# Replace "campaigns" with the app name from the error (e.g. crm, datalab, chatbot, central_hub)
python manage.py migrate campaigns zero --fake
python manage.py migrate
```

If multiple apps fail the same way, repeat for each:

```bash
python manage.py migrate campaigns zero --fake
python manage.py migrate crm zero --fake
# ... etc.
python manage.py migrate
```

**Only use this when the corresponding tables are missing.** If the tables exist and you only need to add `tenant_uuid`, do not use `zero --fake` or you may duplicate tables.
