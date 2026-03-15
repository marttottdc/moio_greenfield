"""
Platform admin KPI aggregation: tenant-by-tenant sweep.
Used by PlatformAdminKPIsView and by Celery task to fill PlatformAdminKpiSnapshot.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from django.db import connection
from django.db.models import Q

from tenancy.tenant_support import tenant_rls_context

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def get_enabled_tenants_for_kpis(tenant_slug: str | None = None) -> list[tuple[int, str]]:
    """
    Return list of (tenant_id, subdomain) for enabled tenants.
    Uses raw SQL with RLS off for the query so we always see all tenants regardless of current RLS context.
    """
    with connection.cursor() as cursor:
        try:
            cursor.execute("SET LOCAL row_level_security = off")
        except Exception:
            pass
        if tenant_slug:
            cursor.execute(
                """
                SELECT id, TRIM(COALESCE(subdomain, ''))
                FROM portal_tenant
                WHERE enabled = true
                  AND (schema_name = %s OR TRIM(COALESCE(subdomain, '')) = %s)
                ORDER BY id
                """,
                [tenant_slug, tenant_slug],
            )
        else:
            cursor.execute(
                """
                SELECT id, TRIM(COALESCE(subdomain, ''))
                FROM portal_tenant
                WHERE enabled = true
                  AND TRIM(COALESCE(subdomain, '')) != ''
                ORDER BY id
                """,
            )
        rows = cursor.fetchall()
    return [(r[0], r[1]) for r in rows if r[1]]


def aggregate_kpis_for_tenant(rls_slug: str, start_dt: datetime | None, end_dt: datetime | None) -> dict:
    """Run count queries inside tenant RLS context. Date filters applied when start_dt/end_dt are set."""
    from crm.models import ActivityRecord, Contact, Customer, Deal
    from flows.models import FlowExecution
    from chatbot.models.agent_session import AgentSession

    with tenant_rls_context(rls_slug):
        contact_filter = Q()
        customer_filter = Q()
        deal_filter = Q()
        activity_filter = Q()
        flow_exec_filter = Q()
        session_filter = Q()
        if start_dt is not None and end_dt is not None:
            contact_filter = Q(created__gte=start_dt, created__lte=end_dt)
            customer_filter = Q(created__gte=start_dt, created__lte=end_dt)
            deal_filter = Q(created_at__gte=start_dt, created_at__lte=end_dt)
            activity_filter = Q(created_at__gte=start_dt, created_at__lte=end_dt)
            flow_exec_filter = Q(started_at__gte=start_dt, started_at__lte=end_dt)
            session_filter = Q(last_interaction__gte=start_dt, last_interaction__lte=end_dt)

        contacts = Contact.objects.filter(contact_filter).count()
        accounts = Customer.objects.filter(customer_filter).count()
        deals = Deal.objects.filter(deal_filter).count()
        activities = ActivityRecord.objects.filter(activity_filter).count()
        flow_executions = FlowExecution.objects.filter(flow_exec_filter).count()
        agent_sessions = AgentSession.objects.filter(session_filter).count()

        return {
            "contacts": contacts,
            "accounts": accounts,
            "deals": deals,
            "activities": activities,
            "flow_executions": flow_executions,
            "agent_sessions": agent_sessions,
        }


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
