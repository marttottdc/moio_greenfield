"""
Effective capabilities resolver: role + tenant entitlements only.

No per-user overrides; users get only what their role and tenant entitlements allow.
1. Capabilities implied by role (ROLE_CAPABILITIES).
2. Intersect with tenant entitlements (tenant cannot be exceeded).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Set

from portal.rbac import ROLE_ORDER, _user_group_names, _role_rank
from portal.entitlements_defaults import get_default_features_for_plan, get_default_limits_for_plan


# Capability keys. Keep in sync with entitlements_defaults features.
CAPABILITY_KEYS = frozenset({
    "crm_contacts_read",
    "crm_contacts_write",
    "campaigns_read",
    "campaigns_send",
    "flows_read",
    "flows_run",
    "flows_edit",
    "settings_integrations_manage",
    "users_manage",
})

# Role -> set of capability keys that role gets by default (before tenant/overrides).
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
        "settings_integrations_manage",
        "users_manage",
    },
    "platform_admin": set(CAPABILITY_KEYS),
}


def _resolve_user_role(user) -> str:
    """Highest RBAC role for user from groups; platform_admin if superuser."""
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
    """Capability keys the tenant allows (features that are True)."""
    if not features:
        return set()
    return {k for k, v in features.items() if v is True and k in CAPABILITY_KEYS}


@dataclass
class EffectiveCapabilities:
    """Resolved capabilities for a user in a tenant context."""
    allowed_capabilities: Set[str]
    effective_features: Dict[str, bool]
    limits: Dict[str, Any]

    def can(self, capability_key: str) -> bool:
        return capability_key in self.allowed_capabilities


def _is_legacy_tenant(tenant_entitlements) -> bool:
    """True if tenant has no entitlements data yet (pre-backfill / legacy)."""
    if tenant_entitlements is None:
        return False
    if hasattr(tenant_entitlements, "features") and hasattr(tenant_entitlements, "limits"):
        return not (tenant_entitlements.features or tenant_entitlements.limits)
    if isinstance(tenant_entitlements, dict):
        return not (tenant_entitlements.get("features") or tenant_entitlements.get("limits"))
    return False


def get_effective_capabilities(user, tenant_entitlements) -> EffectiveCapabilities:
    """
    Compute effective capabilities for a user from role + tenant only (no per-user overrides).

    Legacy tenants (no features/limits set yet) get full access to avoid blocking existing
    users before backfill runs.

    Args:
        user: MoioUser (or user-like with groups, is_superuser).
        tenant_entitlements: Tenant instance (has features, limits) or dict with features, limits.

    Returns:
        EffectiveCapabilities with allowed_capabilities, effective_features, limits.
    """
    features = {}
    limits = {}
    if tenant_entitlements is not None:
        if hasattr(tenant_entitlements, "features"):
            features = dict(tenant_entitlements.features or {})
            if not features:
                plan = getattr(tenant_entitlements, "plan", None)
                features = get_default_features_for_plan(str(plan or "free").lower())
        else:
            features = dict((tenant_entitlements.get("features") or {}))
        if hasattr(tenant_entitlements, "limits"):
            limits = dict(tenant_entitlements.limits or {})
            if not limits:
                plan = getattr(tenant_entitlements, "plan", None)
                limits = get_default_limits_for_plan(str(plan or "free").lower())
        else:
            limits = dict((tenant_entitlements.get("limits") or {}))

    # Legacy tenants (no entitlements data yet): grant full access to avoid deployment conflicts
    if _is_legacy_tenant(tenant_entitlements):
        role = _resolve_user_role(user)
        role_caps = ROLE_CAPABILITIES.get(role, ROLE_CAPABILITIES["member"]).copy()
        # All capability keys allowed by tenant; effective = role intersection (role_caps)
        full_features = {k: (k in role_caps) for k in CAPABILITY_KEYS}
        # Non-capability UI flags on for legacy so UI does not hide anything
        for ui_key in ("crm", "campaigns", "flows"):
            full_features[ui_key] = True
        return EffectiveCapabilities(
            allowed_capabilities=role_caps,
            effective_features=full_features,
            limits=get_default_limits_for_plan("business"),
        )

    tenant_allowed = _tenant_allowed_capabilities(features)
    role = _resolve_user_role(user)
    role_caps = ROLE_CAPABILITIES.get(role, ROLE_CAPABILITIES["member"]).copy()
    allowed = role_caps & tenant_allowed

    # Capability keys: true only if in allowed set
    effective_features = {k: k in allowed for k in tenant_allowed}
    # Non-capability feature flags: pass through from tenant so UI flags (crm, campaigns, flows) are preserved
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
