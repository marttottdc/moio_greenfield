"""Effective capabilities resolver: role + tenant entitlements."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Set

from central_hub.plan_policy import get_default_entitlements_for_plan, get_self_provision_default_plan
from tenancy.rbac import ROLE_ORDER, _user_group_names, _role_rank

# Only these keys are used for permission checks (eff.can()). Plan form may show more "features"
# (e.g. crm, campaigns, flows, chatbot, datalab) which are module/UI flags only, not enforced here.
CAPABILITY_KEYS = frozenset({
    "crm_contacts_read", "crm_contacts_write",
    "campaigns_read", "campaigns_send",
    "flows_read", "flows_run", "flows_edit",
    "settings_integrations_manage", "users_manage",
})

ROLE_CAPABILITIES: Dict[str, Set[str]] = {
    "viewer": {"crm_contacts_read", "campaigns_read", "flows_read"},
    "member": {"crm_contacts_read", "crm_contacts_write", "campaigns_read", "flows_read", "flows_run"},
    "manager": {
        "crm_contacts_read", "crm_contacts_write",
        "campaigns_read", "campaigns_send",
        "flows_read", "flows_run", "flows_edit",
    },
    "tenant_admin": {
        "crm_contacts_read", "crm_contacts_write",
        "campaigns_read", "campaigns_send",
        "flows_read", "flows_run", "flows_edit",
        "settings_integrations_manage", "users_manage",
    },
    "platform_admin": set(CAPABILITY_KEYS),
}


def _resolve_user_role(user) -> str:
    if getattr(user, "is_superuser", False):
        return "platform_admin"
    names = list(_user_group_names(user))
    best_rank = -1
    best_role = "member"
    for role in ROLE_ORDER:
        if role in names:
            r = _role_rank(role)
            if r > best_rank:
                best_rank = r
                best_role = role
    return best_role


def _tenant_allowed_capabilities(features: Dict[str, Any]) -> Set[str]:
    if not features:
        return set()
    return {k for k, v in features.items() if v is True and k in CAPABILITY_KEYS}


@dataclass
class EffectiveCapabilities:
    allowed_capabilities: Set[str]
    effective_features: Dict[str, bool]
    limits: Dict[str, Any]

    def can(self, capability_key: str) -> bool:
        return capability_key in self.allowed_capabilities


def _is_legacy_tenant(tenant_entitlements) -> bool:
    if tenant_entitlements is None:
        return False
    if hasattr(tenant_entitlements, "features") and hasattr(tenant_entitlements, "limits"):
        return not (tenant_entitlements.features or tenant_entitlements.limits)
    if isinstance(tenant_entitlements, dict):
        return not (tenant_entitlements.get("features") or tenant_entitlements.get("limits"))
    return False


def get_effective_capabilities(user, tenant_entitlements) -> EffectiveCapabilities:
    features = {}
    limits = {}
    if tenant_entitlements is not None:
        if hasattr(tenant_entitlements, "features"):
            features = dict(tenant_entitlements.features or {})
            if not features:
                plan = getattr(tenant_entitlements, "plan", None)
                defaults = get_default_entitlements_for_plan(str(plan or get_self_provision_default_plan().key).lower())
                features = dict(defaults.get("features") or {})
        else:
            features = dict((tenant_entitlements.get("features") or {}))
        if hasattr(tenant_entitlements, "limits"):
            limits = dict(tenant_entitlements.limits or {})
            if not limits:
                plan = getattr(tenant_entitlements, "plan", None)
                defaults = get_default_entitlements_for_plan(str(plan or get_self_provision_default_plan().key).lower())
                limits = dict(defaults.get("limits") or {})
        else:
            limits = dict((tenant_entitlements.get("limits") or {}))

    if _is_legacy_tenant(tenant_entitlements):
        role = _resolve_user_role(user)
        role_caps = ROLE_CAPABILITIES.get(role, ROLE_CAPABILITIES["member"]).copy()
        full_features = {k: (k in role_caps) for k in CAPABILITY_KEYS}
        for ui_key in ("crm", "campaigns", "flows"):
            full_features[ui_key] = True
        plan_key = getattr(tenant_entitlements, "plan", None) or get_self_provision_default_plan().key
        return EffectiveCapabilities(
            allowed_capabilities=role_caps,
            effective_features=full_features,
            limits=dict(get_default_entitlements_for_plan(str(plan_key).lower()).get("limits") or {}),
        )

    tenant_allowed = _tenant_allowed_capabilities(features)
    role = _resolve_user_role(user)
    role_caps = ROLE_CAPABILITIES.get(role, ROLE_CAPABILITIES["member"]).copy()
    allowed = role_caps & tenant_allowed
    effective_features = {k: k in allowed for k in tenant_allowed}
    for k, v in features.items():
        if k not in CAPABILITY_KEYS:
            effective_features[k] = bool(v)
        elif k not in effective_features and v is True:
            effective_features[k] = False

    return EffectiveCapabilities(
        allowed_capabilities=allowed,
        effective_features=effective_features,
        limits=limits,
    )
