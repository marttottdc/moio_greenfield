# Platform Admin KPIs (Celery)

Los KPIs de Usage en Platform Admin se sirven **siempre desde la tabla de snapshot** (`platform_admin_kpi_snapshot`). La agregación la hace Celery; la vista HTTP solo lee y, si falta o está obsoleta, encola la tarea.

## Cómo se usa con los tenants

- **Tenant: All**  
  La tarea `refresh_platform_admin_kpi_snapshots` con `tenant_slug=None` recorre todos los tenants (RLS off en una transacción) y escribe una fila con `tenant_id=null` por cada `period_key` (all, 24h, 7d, 30d). La vista lee esa fila.

- **Tenant: uno concreto (ej. acme)**  
  La tarea con `tenant_slug="acme"` agrega solo ese tenant y escribe filas con `tenant_id=X`. La vista, al pedir `?tenant=acme`, lee la fila correspondiente. Si no existe o está obsoleta, encola `refresh_platform_admin_kpi_snapshots.delay(period_keys=[...], tenant_slug="acme")`.

## Tarea Celery

- **Nombre:** `central_hub.tasks.refresh_platform_admin_kpi_snapshots`
- **Argumentos:** `period_keys` (opcional, por defecto `["all", "24h", "7d", "30d"]`), `tenant_slug` (opcional, `None` = todos los tenants).
- **Cola:** `LOW_PRIORITY_Q`

## Programar en Celery Beat (cada 10 min para "All")

Con **django_celery_beat** (DatabaseScheduler) puedes crear una PeriodicTask en el admin o por código:

```python
from django_celery_beat.models import PeriodicTask, IntervalSchedule

schedule, _ = IntervalSchedule.objects.get_or_create(every=10, period="minutes")
PeriodicTask.objects.update_or_create(
    name="platform-admin-kpis-refresh",
    defaults={
        "task": "central_hub.tasks.refresh_platform_admin_kpi_snapshots",
        "interval": schedule,
        "enabled": True,
        "kwargs": "{}",  # tenant_slug=None → refresh "all"
    },
)
```

Así los KPIs de "All" se actualizan cada 10 minutos. Al elegir un tenant en la UI, si no hay snapshot para ese tenant se encola la tarea con ese `tenant_slug` y se devuelve lo que haya (o ceros).
