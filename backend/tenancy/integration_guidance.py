"""Build agent-facing guidance from tenant integration bindings."""
from __future__ import annotations

import re

from tenancy.tenant_support import (
    public_schema_name,
    tenant_schema_context,
    tenants_enabled,
)


def build_tenant_integration_guidance_sync(
    *,
    tenant_schema: str | None,
    max_chars: int = 12000,
    max_integrations: int = 20,
) -> str:
    if not tenants_enabled():
        return ""

    from tenancy.models import Tenant, TenantIntegration

    schema = str(tenant_schema or "").strip().lower()
    if not schema or schema == public_schema_name():
        return ""

    with tenant_schema_context(public_schema_name()):
        tenant = Tenant.objects.filter(schema_name=schema).first()
        if tenant is None:
            return ""

        bindings = list(
            TenantIntegration.objects.select_related("integration")
            .filter(tenant=tenant, is_enabled=True, integration__is_active=True)
            .order_by("integration__key")[: max(1, int(max_integrations))]
        )

    if not bindings:
        return ""

    lines: list[str] = [
        "Use these tenant-enabled integrations when relevant. Prefer them before generic web scraping if they cover the task.",
        "Each item includes assistant-facing documentation curated for this tenant.",
    ]
    for binding in bindings:
        integration = binding.integration
        docs = str(binding.assistant_docs_override or integration.assistant_docs_markdown or "").strip()
        docs = _compact_docs(docs, max_chars=850)
        base_url = str(integration.base_url or "").strip() or "n/a"
        scope = str(getattr(integration, "auth_scope", "tenant") or "tenant")
        lines.append(
            f"- {integration.name or integration.key} (`{integration.key}`) | auth: {integration.default_auth_type} ({scope}) | base: {base_url}"
        )
        if docs:
            lines.append(f"  guidance: {docs}")
        if binding.notes:
            lines.append(f"  tenant notes: {_compact_docs(str(binding.notes), max_chars=260)}")

    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 14].rstrip() + "\n...[truncated]"


def list_tenant_integrations_for_agent_sync(
    *,
    tenant_schema: str | None,
    max_integrations: int = 50,
) -> dict[str, object]:
    if not tenants_enabled():
        return {"enabledCount": 0, "integrations": []}

    from tenancy.models import Tenant, TenantIntegration

    schema = str(tenant_schema or "").strip().lower()
    if not schema or schema == public_schema_name():
        return {"enabledCount": 0, "integrations": []}

    with tenant_schema_context(public_schema_name()):
        tenant = Tenant.objects.filter(schema_name=schema).first()
        if tenant is None:
            return {"enabledCount": 0, "integrations": []}

        bindings = list(
            TenantIntegration.objects.select_related("integration")
            .filter(tenant=tenant, is_enabled=True, integration__is_active=True)
            .order_by("integration__key")[: max(1, int(max_integrations))]
        )

    rows: list[dict[str, object]] = []
    for binding in bindings:
        integration = binding.integration
        docs = str(binding.assistant_docs_override or integration.assistant_docs_markdown or "").strip()
        scope = str(getattr(integration, "auth_scope", "tenant") or "tenant").strip().lower() or "tenant"
        rows.append(
            {
                "key": str(integration.key or "").strip().lower(),
                "name": str(integration.name or integration.key or "").strip(),
                "baseUrl": str(integration.base_url or "").strip(),
                "authType": str(integration.default_auth_type or "").strip().lower(),
                "authScope": scope,
                "hasDocs": bool(docs),
            }
        )

    return {
        "enabledCount": len(rows),
        "integrations": rows,
    }


def _compact_docs(text: str, *, max_chars: int) -> str:
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", str(text).strip())
    if len(compact) <= max_chars:
        return compact
    clipped = compact[: max_chars - 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip() + "\u2026"
