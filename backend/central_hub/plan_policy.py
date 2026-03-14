from __future__ import annotations

from typing import Any

from central_hub.models import Plan


class PlanPolicyError(ValueError):
    """Raised when a plan cannot be resolved from Platform Admin data."""


def _normalize_entitlement_policy(raw: object, plan_key: str) -> dict[str, Any]:
    policy = raw if isinstance(raw, dict) else {}
    features = policy.get("features") if isinstance(policy.get("features"), dict) else {}
    limits = policy.get("limits") if isinstance(policy.get("limits"), dict) else {}
    ui = policy.get("ui") if isinstance(policy.get("ui"), dict) else {}
    return {
        "plan": str(plan_key or "").strip().lower(),
        "features": dict(features),
        "limits": dict(limits),
        "ui": dict(ui),
    }


def get_plan_by_key(plan_key: str, *, active_only: bool = False) -> Plan:
    key = str(plan_key or "").strip().lower()
    if not key:
        raise PlanPolicyError("Plan key is required.")
    query = Plan.objects.filter(key=key)
    if active_only:
        query = query.filter(is_active=True)
    plan = query.first()
    if plan is None:
        raise PlanPolicyError(f"Plan '{key}' is not defined in Platform Admin.")
    return plan


def get_self_provision_default_plan(*, active_only: bool = True) -> Plan:
    query = Plan.objects.filter(is_self_provision_default=True)
    if active_only:
        query = query.filter(is_active=True)
    plan = query.order_by("display_order", "key").first()
    if plan is None:
        raise PlanPolicyError("No self-provision default plan is configured in Platform Admin.")
    return plan


def get_default_entitlements_for_plan(plan_key: str) -> dict[str, Any]:
    plan = get_plan_by_key(plan_key)
    return _normalize_entitlement_policy(plan.entitlement_policy, plan.key)
