import logging
from django.db import transaction

logger = logging.getLogger(__name__)


def sync_tenant_tools(
    *,
    resync: bool = False,
    tool_names: list[str] | None = None,
    tenant_ids: list[int] | None = None,
) -> None:
    """
    Sync FunctionTools into TenantToolConfiguration.

    Filters:
    - tool_names: only sync these tools
    - tenant_ids: only sync these tenants

    Modes:
    - soft sync (default): preserves tenant customizations
    - hard resync: overwrites tenant customizations
    """
    from central_hub.models import Tenant
    from chatbot.models.tenant_tool_configuration import TenantToolConfiguration
    from chatbot.agents.moio_agents_loader import get_available_tools

    tools = get_available_tools()

    # 🔎 filter tools
    if tool_names:
        tool_names_set = set(tool_names)
        tools = [t for t in tools if t.name in tool_names_set]

    tenants_qs = Tenant.objects.all()

    # 🔎 filter tenants
    if tenant_ids:
        tenants_qs = tenants_qs.filter(id__in=tenant_ids)

    logger.info(
        "Starting tenant tool sync | tenants=%s tools=%s resync=%s tool_filter=%s tenant_filter=%s",
        tenants_qs.count(),
        len(tools),
        resync,
        tool_names,
        tenant_ids,
    )

    for tenant in tenants_qs:
        try:
            with transaction.atomic():
                for tool in tools:
                    tool_name = tool.name
                    tool_description = tool.description or ""
                    tool_schema = tool.params_json_schema or {}
                    tool_enabled = tool.is_enabled
                    tool_display_name = tool_name.replace("_", " ").title()

                    obj, created = TenantToolConfiguration.objects.get_or_create(
                        tenant=tenant,
                        tool_name=tool_name,
                        defaults={
                            "tool_type": "custom",
                            "enabled": tool_enabled,
                            "custom_display_name": tool_display_name,
                            "custom_description": tool_description,
                            "default_params": tool_schema,
                        },
                    )

                    if created:
                        logger.info(
                            "Created tool config | tenant=%s tool=%s",
                            tenant.id,
                            tool_name,
                        )
                        continue

                    fields_to_update = []

                    # Enabled flag follows source of truth
                    if obj.enabled != tool_enabled:
                        obj.enabled = tool_enabled
                        fields_to_update.append("enabled")

                    if obj.tool_type != "custom":
                        obj.tool_type = "custom"
                        fields_to_update.append("tool_type")

                    if resync:
                        # HARD overwrite
                        if obj.custom_display_name != tool_display_name:
                            obj.custom_display_name = tool_display_name
                            fields_to_update.append("custom_display_name")

                        if obj.custom_description != tool_description:
                            obj.custom_description = tool_description
                            fields_to_update.append("custom_description")

                        if obj.default_params != tool_schema:
                            obj.default_params = tool_schema
                            fields_to_update.append("default_params")

                    else:
                        # SOFT sync → merge schema (tenant wins)
                        merged_schema = {
                            **tool_schema,
                            **(obj.default_params or {}),
                        }

                        if merged_schema != obj.default_params:
                            obj.default_params = merged_schema
                            fields_to_update.append("default_params")

                    if fields_to_update:
                        obj.save(update_fields=fields_to_update)

                        logger.info(
                            "Updated tool config | tenant=%s tool=%s fields=%s",
                            tenant.id,
                            tool_name,
                            fields_to_update,
                        )

        except Exception:
            logger.exception(
                "Error syncing tools for tenant %s",
                tenant.id,
            )
            continue

    logger.info("Tenant tool sync finished")
