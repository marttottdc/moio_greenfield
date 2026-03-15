"""
Platform admin KPI aggregation: tenant-by-tenant sweep.
Used by PlatformAdminKPIsView and by Celery task to fill PlatformAdminKpiSnapshot.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from django.db import connection, transaction
from django.db.models import Q

from tenancy.models import Tenant
from tenancy.tenant_support import tenant_rls_context

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def get_enabled_tenants_for_kpis(tenant_slug: str | None = None) -> list[tuple[int, str]]:
    """
    Return list of (tenant_id, subdomain) for enabled tenants. ORM only, no RLS off.
    In a Celery worker with no tenant context, prefer passing tenant_slugs from the caller.
    """
    qs = Tenant.objects.filter(enabled=True).exclude(subdomain="").exclude(subdomain__isnull=True)
    if tenant_slug:
        slug = (tenant_slug or "").strip()
        qs = qs.filter(Q(schema_name=slug) | Q(subdomain=slug))
    qs = qs.order_by("id").values_list("id", "subdomain")
    result = [(row[0], (row[1] or "").strip()) for row in qs if (row[1] or "").strip()]
    logger.debug("Platform KPIs: get_enabled_tenants_for_kpis found %s tenants", len(result))
    return result


# Table names for raw count queries (same connection as SET LOCAL; ORM goes through django_rls and can lose context).
_KPI_TABLES = (
    ("contacts", "crm_contact"),
    ("accounts", "crm_customer"),
    ("deals", "crm_deal"),
    ("activities", "crm_activityrecord"),
    ("flow_executions", "flows_flowexecution"),
    ("agent_sessions", "chatbot_agentsession"),
)


def aggregate_kpis_for_tenant(rls_slug: str, start_dt: datetime | None, end_dt: datetime | None) -> dict:
    """Run count queries inside tenant RLS context. Use raw SQL so counts see SET LOCAL (ORM can use different path)."""
    with transaction.atomic():
        with tenant_rls_context(rls_slug):
            out = {}
            with connection.cursor() as cur:
                for key, table in _KPI_TABLES:
                    try:
                        quoted = connection.ops.quote_name(table)
                        cur.execute("SELECT count(*) FROM " + quoted)
                        out[key] = (cur.fetchone() or (0,))[0]
                    except Exception:
                        out[key] = 0
            return out


def run_full_sweep(
    tenant_slug: str | None = None,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
) -> dict:
    """
    Sweep all enabled tenants (or one if tenant_slug set), aggregate KPIs, return totals.
    """
    tenant_list = get_enabled_tenants_for_kpis(tenant_slug)
    if not tenant_list:
        logger.info("Platform KPIs sweep: no enabled tenants found (tenant_slug=%s)", tenant_slug)
        return {
            "contacts": 0,
            "accounts": 0,
            "deals": 0,
            "activities": 0,
            "flow_executions": 0,
            "agent_sessions": 0,
        }

    totals = {
        "contacts": 0,
        "accounts": 0,
        "deals": 0,
        "activities": 0,
        "flow_executions": 0,
        "agent_sessions": 0,
    }
    errors = 0
    for tenant_id, subdomain in tenant_list:
        try:
            data = aggregate_kpis_for_tenant(subdomain, start_dt, end_dt)
            logger.info(
                "Platform KPIs sweep tenant=%s: contacts=%s accounts=%s activities=%s",
                subdomain,
                data.get("contacts", 0),
                data.get("accounts", 0),
                data.get("activities", 0),
            )
            for k in totals:
                totals[k] += data.get(k, 0)
        except Exception as exc:
            errors += 1
            logger.warning(
                "Platform KPIs sweep: failed for tenant id=%s subdomain=%s: %s",
                tenant_id,
                subdomain,
                exc,
                exc_info=False,
            )
    if errors:
        logger.info("Platform KPIs sweep: completed with %s errors across %s tenants", errors, len(tenant_list))
    return totals


def run_full_sweep_over_slugs(
    rls_slugs: list[str],
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
) -> dict:
    """
    Sweep over an explicit list of tenant rls_slugs (subdomains); no tenant discovery.
    Caller is responsible for passing the list (e.g. from get_enabled_tenants_for_kpis).
    """
    if not rls_slugs:
        return {
            "contacts": 0,
            "accounts": 0,
            "deals": 0,
            "activities": 0,
            "flow_executions": 0,
            "agent_sessions": 0,
        }
    totals = {
        "contacts": 0,
        "accounts": 0,
        "deals": 0,
        "activities": 0,
        "flow_executions": 0,
        "agent_sessions": 0,
    }
    errors = 0
    for slug in rls_slugs:
        try:
            data = aggregate_kpis_for_tenant(slug, start_dt, end_dt)
            logger.info(
                "Platform KPIs sweep tenant=%s: contacts=%s accounts=%s activities=%s",
                slug,
                data.get("contacts", 0),
                data.get("accounts", 0),
                data.get("activities", 0),
            )
            for k in totals:
                totals[k] += data.get(k, 0)
        except Exception as exc:
            errors += 1
            logger.warning(
                "Platform KPIs sweep (over slugs): failed for slug=%s: %s",
                slug,
                exc,
                exc_info=False,
            )
    if errors:
        logger.info(
            "Platform KPIs sweep (over slugs): completed with %s errors across %s slugs",
            errors,
            len(rls_slugs),
        )
    return totals


def run_full_sweep_rls_off(
    tenant_slug: str | None = None,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
) -> dict:
    """
    Same as run_full_sweep but with RLS off for the whole sweep (single transaction).
    Intended for Celery: worker has no request tenant, so we can disable RLS and loop
    count(Contact, tenant_id=X) etc. without setting app.current_tenant_slug per tenant.
    """
    from crm.models import ActivityRecord, Contact, Customer, Deal
    from flows.models import FlowExecution
    from chatbot.models.agent_session import AgentSession
    from tenancy.models import Tenant

    with transaction.atomic():
        with connection.cursor() as cursor:
            try:
                cursor.execute("SET LOCAL row_level_security = off")
            except Exception:
                pass
        tenants = list(
            Tenant.objects.filter(enabled=True)
            .exclude(subdomain="")
            .only("id", "subdomain", "schema_name")
        )
        if tenant_slug:
            slug = (tenant_slug or "").strip()
            tenants = [t for t in tenants if ((t.subdomain or "").strip() == slug) or (getattr(t, "schema_name", None) or "") == slug]
        if not tenants:
            return {
                "contacts": 0,
                "accounts": 0,
                "deals": 0,
                "activities": 0,
                "flow_executions": 0,
                "agent_sessions": 0,
            }
        totals = {"contacts": 0, "accounts": 0, "deals": 0, "activities": 0, "flow_executions": 0, "agent_sessions": 0}
        base_contact = Q()
        base_customer = Q()
        base_deal = Q()
        base_activity = Q()
        base_flow_exec = Q()
        base_session = Q()
        if start_dt is not None and end_dt is not None:
            base_contact = Q(created__gte=start_dt, created__lte=end_dt)
            base_customer = Q(created__gte=start_dt, created__lte=end_dt)
            base_deal = Q(created_at__gte=start_dt, created_at__lte=end_dt)
            base_activity = Q(created_at__gte=start_dt, created_at__lte=end_dt)
            base_flow_exec = Q(started_at__gte=start_dt, started_at__lte=end_dt)
            base_session = Q(last_interaction__gte=start_dt, last_interaction__lte=end_dt)
        for tenant in tenants:
            tid = tenant.id
            totals["contacts"] += Contact.objects.filter(base_contact, tenant_id=tid).count()
            totals["accounts"] += Customer.objects.filter(base_customer, tenant_id=tid).count()
            totals["deals"] += Deal.objects.filter(base_deal, tenant_id=tid).count()
            totals["activities"] += ActivityRecord.objects.filter(base_activity, tenant_id=tid).count()
            totals["flow_executions"] += FlowExecution.objects.filter(base_flow_exec, flow__tenant_id=tid).count()
            totals["agent_sessions"] += AgentSession.objects.filter(base_session, tenant_id=tid).count()
    return totals
