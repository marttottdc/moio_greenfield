"""
Default tenant entitlements (features + limits) by plan.
Used to seed Tenant.features, Tenant.limits, Tenant.ui on tenant creation.
"""
from __future__ import annotations

from typing import Any, Dict

# Plan identifiers must match Tenant.Plan values
FREE = "free"
PRO = "pro"
BUSINESS = "business"


def get_default_features_for_plan(plan: str) -> Dict[str, bool]:
    """Feature flags by plan. Free tier: CRM only, 5 users, no flows, no chatbot."""
    base = {
        "crm": True,
        "crm_contacts_read": True,
        "crm_contacts_write": True,
        "campaigns": False,
        "campaigns_read": False,
        "campaigns_send": False,
        "flows": False,
        "flows_read": False,
        "flows_run": False,
        "flows_edit": False,
        "chatbot": False,
        "datalab": False,
        "settings_integrations_manage": False,
        "users_manage": False,
    }
    if plan == FREE:
        return base
    if plan == PRO:
        out = dict(base)
        out["flows"] = True
        out["flows_read"] = True
        out["flows_run"] = True
        out["flows_edit"] = True
        out["chatbot"] = True
        out["datalab"] = True
        out["users_manage"] = True
        return out
    if plan == BUSINESS:
        out = dict(base)
        out["campaigns"] = True
        out["campaigns_read"] = True
        out["campaigns_send"] = True
        out["flows"] = True
        out["flows_read"] = True
        out["flows_run"] = True
        out["flows_edit"] = True
        out["chatbot"] = True
        out["datalab"] = True
        out["settings_integrations_manage"] = True
        out["users_manage"] = True
        return out
    return base


def get_default_limits_for_plan(plan: str) -> Dict[str, Any]:
    """Numeric/limit defaults by plan. Free: 5 users, no flows, no agents."""
    if plan == BUSINESS:
        return {"seats": 50, "agents": 10, "flows": 100}
    if plan == PRO:
        return {"seats": 10, "agents": 3, "flows": 20}
    return {"seats": 5, "agents": 0, "flows": 0}


def get_default_entitlements_for_plan(plan: str) -> Dict[str, Any]:
    """Return features, limits, and optional ui for Tenant (on create or backfill)."""
    plan_lc = (plan or FREE).lower()
    return {
        "plan": plan_lc if plan_lc in (FREE, PRO, BUSINESS) else FREE,
        "features": get_default_features_for_plan(plan_lc),
        "limits": get_default_limits_for_plan(plan_lc),
        "ui": {},
    }
