import html
import json
import logging
import time
import uuid
from datetime import timedelta
from copy import deepcopy
from typing import Dict, Any, Iterable
import textwrap
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


from django.conf import settings
from moio_platform.settings import FLOWS_Q
from django.contrib.auth.decorators import login_required
from django.http import (
    JsonResponse,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
    HttpRequest,
    Http404,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.timezone import now
from django.db import transaction
from django.db.models import Q, Max, Prefetch, Count, Avg
from django.db.models.functions import Lower
from django.utils.formats import date_format
from django.utils.text import slugify
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from central_hub.context_utils import current_tenant
from .core.compiler import (
    FlowCompilationError,
    compile_flow_graph,
    compile_published_version,
    register_definition,
    unregister_flow,
)
from .core.connector import trigger_manual_flow as trigger_manual_flow_helper
from .core.runtime import FlowRun


try:  # pragma: no cover - optional dependency in minimal test settings
    from crm.models import WebhookConfig
except Exception:  # pragma: no cover
    WebhookConfig = None

from .models import (
    Flow,
    FlowVersion,
    FlowVersionStatus,
    FlowExecution,
    FlowScript,
    FlowScriptLog,
    FlowScriptRun,
    FlowScriptVersion,
)
from .core.schema import FlowGraph, GraphValidationError, validate_graph_payload
from .registry import REGISTRY, serialize_definitions, palette_by_category
from .validation import normalize_graph
from .scripts import FlowScriptSerializer
from .serializers import FlowCreateSerializer
from .scripts.tasks import execute_script_run
from .scripts.validators import validate_script_payload
from .tasks import preview_flow


class VersionConflictError(Exception):
    """Raised when an optimistic locking version conflict is detected."""
    
    def __init__(self, expected_version_id: str | None, current_version_id: str | None):
        self.expected_version_id = expected_version_id
        self.current_version_id = current_version_id
        super().__init__(
            f"Version conflict: expected {expected_version_id}, current is {current_version_id}"
        )


def _check_version_conflict(flow: Flow, expected_version_id: str | None) -> FlowVersion | None:
    """
    Check if the expected version matches the current version.
    Returns the current version if valid, raises VersionConflictError if mismatch.
    If expected_version_id is None, no check is performed (backward compatibility).
    """
    current_version = flow.versions.order_by("-created_at").first()
    
    if expected_version_id is None:
        return current_version
    
    current_id = str(current_version.id) if current_version else None
    if current_id != str(expected_version_id):
        raise VersionConflictError(str(expected_version_id), current_id)
    
    return current_version


def _version_conflict_response(exc: VersionConflictError) -> Response:
    """Create a standardized 409 Conflict response for version conflicts."""
    return Response(
        {
            "ok": False,
            "error": "version_conflict",
            "message": "Flow has been modified by another user or session. Please refresh and try again.",
            "expected_version_id": exc.expected_version_id,
            "current_version_id": exc.current_version_id,
        },
        status=409,
    )


def preview_execute(graph: dict, payload: dict | None = None, *, tenant_id=None):
    """Execute a flow graph synchronously for preview purposes."""

    run = FlowRun(
        graph,
        payload or {},
        config=graph.get("config") if isinstance(graph, dict) else None,
        tenant_id=tenant_id,
        trigger={"source": "preview"},
    )
    snapshot = run.execute()
    return {
        "context": snapshot.get("context", {}),
        "timeline": snapshot.get("steps", []),
        "snapshot": snapshot,
    }


def _serialize_webhook_config(webhook: WebhookConfig, request=None):
    schema_raw = webhook.expected_schema or ""
    parsed_schema = _load_schema(schema_raw)
    schema_valid = parsed_schema is not None or not schema_raw
    if parsed_schema is None:
        parsed_schema = {}

    webhook_url = webhook.url or ""
    if request is not None:
        try:
            computed_url = request.build_absolute_uri(
                reverse("generic_webhook_receiver", args=[webhook.id])
            )
        except Exception:
            computed_url = ""
        webhook_url = webhook_url or computed_url

    return {
        "id": str(webhook.id),
        "name": webhook.name,
        "description": webhook.description,
        "url": webhook_url,
        "schema": parsed_schema,
        "schema_text": schema_raw,
        "schema_valid": schema_valid,
        "expected_content_type": webhook.expected_content_type or "",
        "auth_type": webhook.auth_type,
    }

# ---------- Helpers ----------


def _available_webhooks_for_flow(flow: Flow) -> list[dict[str, Any]]:
    """Return webhook configs compatible with flow webhook triggers."""

    if WebhookConfig is None:
        return []

    flow_marker = f"flow:{flow.id}"
    queryset = (
        WebhookConfig.objects.filter(
            tenant=flow.tenant,
            handler_path="flows.handlers.execute_flow_webhook",
        )
        .filter(
            Q(description__icontains=flow_marker)
            | Q(description__isnull=True)
            | Q(description__exact="")
        )
        .order_by("name")
        .values("id", "name", "description", "url", "handler_path")
    )

    webhooks: list[dict[str, Any]] = []
    for webhook in queryset:
        webhook_dict = dict(webhook)
        webhook_dict["id"] = str(webhook_dict.get("id"))
        webhooks.append(webhook_dict)
    return webhooks


def _flatten_whatsapp_placeholders(requirements: Iterable[Dict[str, Any]] | None) -> list[dict[str, Any]]:
    placeholders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for component in requirements or []:
        if not isinstance(component, dict):
            continue
        comp_type = str(component.get("type") or "").lower() or "value"
        parameters = component.get("parameters") or []
        for index, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                continue
            label = parameter.get("parameter_name") or parameter.get("text") or parameter.get("name") or parameter.get("type") or f"{comp_type}_{index + 1}"
            base_slug = slugify(str(label)) if label is not None else ""
            key_base = f"{comp_type}_{base_slug}" if base_slug else f"{comp_type}_{index + 1}"
            key = key_base
            suffix = 1
            while key in seen:
                suffix += 1
                key = f"{key_base}_{suffix}"
            seen.add(key)
            placeholders.append(
                {
                    "key": key,
                    "label": label,
                    "component": comp_type,
                    "type": parameter.get("type") or "",
                    "parameter": parameter.get("parameter_name") or parameter.get("text") or "",
                }
            )
    return placeholders


def _blank_graph() -> dict[str, Any]:
    """Return an empty starter graph for a new flow."""

    graph = {"nodes": [], "edges": [], "meta": {"draft": True}}
    return FlowGraph.model_validate(graph).as_dict()


def _stats_for(tenant=None):
    qs = Flow.objects.all()
    if tenant: qs = qs.filter(tenant=tenant)
    
    versions = FlowVersion.objects.filter(flow__in=qs)
    published = versions.filter(status=FlowVersionStatus.PUBLISHED).values("flow_id").distinct().count()
    drafts = versions.filter(status=FlowVersionStatus.DRAFT).values("flow_id").distinct().count()
    
    # Enabled flows require a published version and status=active.
    active = qs.filter(published_version__isnull=False, status="active").count()
    
    return dict(
        total=qs.count(),
        active=active,
        published=published,
        drafts=drafts,
    )


def _analytics_for(tenant=None, *, days: int = 7) -> dict[str, Any]:
    """Basic execution analytics for the Flows list page (best-effort)."""
    qs = FlowExecution.objects.select_related("flow").all()
    if tenant:
        qs = qs.filter(flow__tenant=tenant)
    since = now() - timedelta(days=days)
    recent = qs.filter(started_at__gte=since)

    by_status = {
        (row.get("status") or "unknown"): int(row.get("count") or 0)
        for row in recent.values("status").annotate(count=Count("id"))
    }
    by_trigger = {
        (row.get("trigger_source") or "unknown"): int(row.get("count") or 0)
        for row in recent.values("trigger_source").annotate(count=Count("id"))
    }

    return {
        "window_days": days,
        "total_runs": recent.count(),
        "by_status": by_status,
        "by_trigger_source": by_trigger,
        "latest_runs": [
            {
                "id": str(e.id),
                "flow_id": str(e.flow_id),
                "flow_name": e.flow.name,
                "status": e.status,
                "trigger_source": e.trigger_source,
                "started_at": e.started_at.isoformat() if e.started_at else None,
            }
            for e in recent.order_by("-started_at")[:10]
        ],
    }


def _json_body(request: HttpRequest) -> dict:
    try:
        body = request.body.decode("utf-8") if request.body else "{}"
    except AttributeError:
        body = "{}"
    if not body:
        body = "{}"
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def _pretty_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except TypeError:
        return json.dumps(_coerce_jsonable(data), indent=2, ensure_ascii=False)


def _flow_queryset_for_request(request: HttpRequest):
    queryset = Flow.objects.all()
    tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
    if tenant_id:
        queryset = queryset.filter(tenant_id=tenant_id)
    return queryset


def _get_flow_for_request(request: HttpRequest, flow_id: str) -> Flow:
    queryset = _flow_queryset_for_request(request)
    return get_object_or_404(queryset, id=flow_id)


def _serialize_flow_version(version: FlowVersion | None, include_graph: bool = False) -> dict[str, Any] | None:
    """Serialize a FlowVersion to dict."""
    if not version:
        return None
    
    data = {
        "id": str(version.id),
        "flow_id": str(version.flow_id),
        "version": version.version,
        "major": version.version,  # Backward compat
        "minor": 0,  # Backward compat
        "label": version.version_label,
        "status": version.status,
        "status_display": version.get_status_display(),
        "is_published": version.is_published,
        "is_testing": version.is_testing,
        "is_draft": version.is_draft,
        "is_archived": version.is_archived,
        "is_active": version.is_published,
        "is_editable": version.is_editable,
        "preview_armed": version.is_testing,  # Backward compat
        "preview_armed_at": version.testing_started_at.isoformat() if version.testing_started_at else None,
        "notes": version.notes,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "updated_at": version.updated_at.isoformat() if version.updated_at else None,
        "published_at": version.published_at.isoformat() if version.published_at else None,
    }
    
    if include_graph:
        data["graph"] = version.graph
        data["config_schema"] = getattr(version, "config_schema", {}) or {}
        data["config_values"] = getattr(version, "config_values", {}) or {}
        try:
            from flows.core.internal_contract import compile_ctx_schema
            data["ctx_schema"] = compile_ctx_schema(version.graph or {})
        except Exception:
            data["ctx_schema"] = {}
    return data


def _serialize_flow(flow: Flow, include_versions: bool = False) -> dict[str, Any]:
    versions = flow._cached_versions() if include_versions else []
    latest = flow.latest_version
    data: dict[str, Any] = {
        "id": str(flow.id),
        "name": flow.name,
        "description": flow.description,
        "status": flow.status,
        "is_enabled": flow.is_enabled,
        # Execution stats (stored on Flow for fast list rendering)
        "execution_count": int(getattr(flow, "execution_count", 0) or 0),
        "last_executed_at": flow.last_executed_at.isoformat() if getattr(flow, "last_executed_at", None) else None,
        "last_execution_status": (flow.last_execution_status or None) if hasattr(flow, "last_execution_status") else None,
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
        "created_by": {
            "id": str(flow.created_by_id) if flow.created_by_id else None,
            "name": getattr(flow.created_by, "get_full_name", lambda: None)() or getattr(flow.created_by, "username", None),
        },
        "current_version_id": str(latest.id) if latest else None,
        "latest_version": _serialize_flow_version(latest),
        "published_version": _serialize_flow_version(flow.published_version),
    }
    if include_versions:
        data["versions"] = [_serialize_flow_version(version) for version in versions]
    return data


def _serialize_execution(execution: FlowExecution) -> dict[str, Any]:
    ctx = execution.execution_context or {}
    trigger_meta = ctx.get("trigger_metadata", {})
    return {
        "id": str(execution.id),
        "flow_id": str(execution.flow_id),
        "flow_name": execution.flow.name if execution.flow else None,
        "status": execution.status,
        "status_display": execution.get_status_display() if hasattr(execution, "get_status_display") else execution.status.title(),
        "execution_mode": ctx.get("execution_mode", "unknown"),
        "trigger_source": execution.trigger_source or ctx.get("trigger_source", "unknown"),
        "sandbox": ctx.get("sandbox", False),
        "duration_ms": execution.duration_ms,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "input": execution.input_data or {},
        "output": execution.output_data or {},
        "error": execution.error_data or {},
        "context": ctx,
        "timeline": ctx.get("timeline", []),
        "graph_version": ctx.get("graph_version"),
        "version_id": ctx.get("version_id"),
        "version_status": ctx.get("version_status"),
        "trace_id": ctx.get("trace_id"),
        "webhook_id": trigger_meta.get("webhook", {}).get("id") if trigger_meta else None,
        "webhook_name": trigger_meta.get("webhook", {}).get("name") if trigger_meta else None,
    }


def _flow_api_endpoints(flow: Flow) -> dict[str, str]:
    endpoints = {
        "detail": reverse("flows_api:api_flow_detail", args=[flow.id]),
        "list": reverse("flows_api:api_flow_list"),
        "save": reverse("flows_api:api_flow_save", args=[flow.id]),
        "validate": reverse("flows_api:api_flow_validate", args=[flow.id]),
        "preview": reverse("flows_api:api_flow_preview", args=[flow.id]),
        "webhooks": reverse("flows:available_webhooks", args=[flow.id]),
    }
    fake_run_id = uuid.uuid4()
    preview_status_url = reverse(
        "flows_api:api_flow_preview_status",
        args=[flow.id, fake_run_id],
    )
    endpoints["preview_status"] = preview_status_url.replace(str(fake_run_id), "{run_id}")
    return endpoints


def _coerce_jsonable(value: Any):
    if value is None:
        return {}
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, (set, tuple)):
            return list(value)
        if isinstance(value, dict):
            return {str(k): _coerce_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, int, float, str, bool)):
            return value
        return str(value)


def _serialize_script(script: FlowScript | None, tenant=None) -> dict[str, Any]:
    if not script or not getattr(script, "id", None):
        params = DEFAULT_SCRIPT_PARAMS
        latest_version = {
            "id": None,
            "version": 1,
            "code": DEFAULT_SCRIPT_CODE,
            "parameters": params,
            "parameters_text": _pretty_json(params),
            "is_published": False,
        }
        default_name = _next_script_name(tenant, "New script") if tenant else "New script"
        return {
            "id": None,
            "name": default_name,
            "description": "",
            "latest_version": latest_version,
            "published_version": None,
            "versions": [],
            "is_published": False,
            "params_text": latest_version["parameters_text"],
        }

    payload = FlowScriptSerializer.serialize(script, include_versions=True)

    # Ensure the ID field is always included as string
    payload["id"] = str(script.id)

    latest = payload.get("latest_version") or {}
    if not latest:
        params = DEFAULT_SCRIPT_PARAMS
        latest = {
            "id": None,
            "version": 1,
            "code": DEFAULT_SCRIPT_CODE,
            "parameters": params,
            "parameters_text": _pretty_json(params),
            "is_published": False,
        }
    else:
        if "parameters" not in latest:
            latest["parameters"] = script.latest_version.parameters if script.latest_version else {}
        latest["parameters_text"] = _pretty_json(latest.get("parameters") or {})
        if "code" not in latest:
            latest["code"] = script.latest_version.code if script.latest_version else DEFAULT_SCRIPT_CODE

    payload["latest_version"] = latest
    payload["is_published"] = payload.get("published_version") is not None
    payload["params_text"] = latest.get("parameters_text", "{}")
    return payload


def _serialize_run(run: FlowScriptRun) -> dict[str, Any]:
    version = getattr(run, "version", None)
    return {
        "id": str(run.id),
        "status": run.status,
        "status_display": run.get_status_display(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "started_at_display": date_format(run.started_at, "DATETIME_FORMAT") if run.started_at else "",
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": run.duration_ms,
        "input_payload": run.input_payload or {},
        "output_payload": run.output_payload or {},
        "error_payload": run.error_payload or {},
        "version": {
            "id": str(version.id) if version else None,
            "version": version.version_number if version else None,
        },
        "has_logs": run.logs.exists(),
    }


def _script_endpoints(script: FlowScript | None) -> dict[str, str]:
    endpoints = {
        "list": reverse("flows:script_list"),
        "builder_new": reverse("flows:script_builder_new"),
        "validate": reverse("flows:script_validate"),
        "save": reverse("flows:script_save_new"),
        "publish": "",
        "run": "",
        "log_stream": "",
    }
    if script and getattr(script, "id", None):
        endpoints.update(
            {
                "builder": f"{reverse('flows:script_builder')}?script_id={script.id}",
                "validate": reverse("flows:script_validate"),
                "save": reverse("flows:script_save_new"),
                "publish": reverse("flows:script_publish"),
                "run": reverse("flows:script_run"),
            }
        )
        fake_run_id = uuid.uuid4()
        stream_url = reverse("flows:script_log_stream", args=[fake_run_id])
        endpoints["log_stream"] = stream_url.replace(str(fake_run_id), "{run_id}")
    return endpoints


def _script_runs_for(script: FlowScript | None, limit: int = 15) -> list[dict[str, Any]]:
    if not script or not getattr(script, "id", None):
        return []
    runs = (
        script.runs.select_related("version")
        .order_by("-started_at")[:limit]
    )
    return [_serialize_run(run) for run in runs]


def _extract_params(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    params = payload.get("params")
    if isinstance(params, dict):
        return params, None
    params_text = (
        payload.get("params_text")
        or payload.get("paramsText")
        or payload.get("raw_params")
        or ""
    )
    if isinstance(params_text, str) and params_text.strip():
        try:
            return json.loads(params_text), None
        except json.JSONDecodeError as exc:
            return {}, f"Invalid JSON: {exc.msg} (line {exc.lineno})"
    return {}, None

# ---------- Views ----------


@login_required
def flow_list(request):
    tenant = getattr(getattr(request, "user", None), "tenant", None)
    flows = (
        _flow_queryset_for_request(request)
        .select_related("tenant", "created_by", "published_version")
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=FlowVersion.objects.order_by("-created_at"),
                to_attr="version_list",
            )
        )
    )
    stats = _stats_for(tenant=tenant)
    analytics = _analytics_for(tenant=tenant, days=7)
    return render(
        request,
        "flows/flow_list.html",
        {"flows": flows, "stats": stats, "analytics": analytics},
    )


def _next_flow_name(tenant, base="New workflow"):
    # Busca colisiones case-insensitive y añade sufijo incremental
    existing = (
        Flow.objects.filter(tenant=tenant)
        .annotate(name_l=Lower("name"))
        .values_list("name_l", flat=True)
    )
    base_l = base.lower()
    if base_l not in existing:
        return base
    i = 2
    while True:
        candidate = f"{base} {i}"
        if candidate.lower() not in existing:
            return candidate
        i += 1


def _next_script_name(tenant, base="New script", exclude_id=None):
    qs = FlowScript.objects.all()
    if tenant:
        qs = qs.filter(tenant=tenant)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    existing = qs.annotate(name_l=Lower("name")).values_list("name_l", flat=True)
    base_l = (base or "New script").lower()
    if base_l not in existing:
        return base or "New script"
    i = 2
    while True:
        candidate = f"{base} {i}" if base else f"New script {i}"
        if candidate.lower() not in existing:
            return candidate
        i += 1


def _unique_script_slug(name: str, tenant) -> str:
    base_slug = slugify(name) or "script"
    slug_candidate = base_slug
    qs = FlowScript.objects.all()
    if tenant:
        qs = qs.filter(tenant=tenant)
    suffix = 2
    while qs.filter(slug=slug_candidate).exists():
        slug_candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return slug_candidate


@require_http_methods(["POST"])
def flow_create(request):
    tenant = getattr(getattr(request, "user", None), "tenant", None)
    base_name = request.POST.get("name") or "New workflow"
    name = _next_flow_name(tenant, base_name)

    f = Flow.objects.create(
        tenant=tenant,
        name=name,
        description="",
        status="inactive",
        created_by=getattr(request, "user", None),
    )
    FlowVersion.objects.create(
        flow=f,
        tenant=tenant,
        version=1,
        status=FlowVersionStatus.DRAFT,
        graph=_blank_graph()
    )
    return HttpResponseRedirect(reverse("flows:builder_react", args=[f.id]))


@login_required
@require_http_methods(["GET"])
def whatsapp_templates(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id)
    user_tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
    if user_tenant_id and flow.tenant_id and user_tenant_id != flow.tenant_id:
        raise Http404("Flow not found")

    tenant = getattr(flow, "tenant", None)
    if tenant is None:
        return JsonResponse(
            {"templates": [], "error": "Tenant not associated with this flow."}, status=400
        )

    config = tenant.configuration.first() if hasattr(tenant, "configuration") else None
    if not config or not getattr(config, "whatsapp_integration_enabled", False):
        return JsonResponse(
            {
                "templates": [],
                "error": "WhatsApp integration is not enabled for this tenant.",
            }
        )

    try:
        from chatbot.lib.whatsapp_client_api import (  # type: ignore
            WhatsappBusinessClient,
            template_requirements,
        )
    except Exception as exc:  # pragma: no cover - optional dependency
        return JsonResponse(
            {"templates": [], "error": f"WhatsApp client unavailable: {exc}"}, status=500
        )

    templates: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        client = WhatsappBusinessClient(config)
        remote_templates = client.download_message_templates() or []
        for template in remote_templates:
            requirements = template_requirements(template) or []
            placeholders = _flatten_whatsapp_placeholders(requirements)
            templates.append(
                {
                    "id": str(template.get("id") or template.get("name") or ""),
                    "name": template.get("name") or template.get("id") or "",
                    "category": template.get("category") or "",
                    "language": template.get("language") or "",
                    "status": template.get("status") or "",
                    "components": template.get("components", []),
                    "requirements": requirements,
                    "placeholders": placeholders,
                }
            )
    except Exception as exc:  # pragma: no cover - defensive
        error_message = str(exc)

    payload: dict[str, Any] = {"templates": templates}
    if error_message:
        payload["error"] = error_message
    return JsonResponse(payload)


def _flow_builder_page_context(
    request: HttpRequest,
    flow: Flow,
    version: FlowVersion | None,
    available_webhooks: list[dict[str, Any]],
):
    source_graph = version.graph if version else _blank_graph()
    try:
        graph_model = normalize_graph(source_graph)
    except Exception:
        graph_model = normalize_graph(_blank_graph())
    graph = _graph_model_to_dict(graph_model)

    builder_stage = request.GET.get("stage")
    if builder_stage:
        builder_stage = builder_stage.strip().lower() or None
    if not builder_stage:
        builder_stage = "dev" if settings.DEBUG else "prod"

    palette = [
        {"label": label, "items": definitions}
        for label, definitions in sorted(
            palette_by_category(stage=builder_stage).items()
        )
    ]

    context = {
        "flow": flow,
        "version": version,
        "available_webhooks": available_webhooks,
        "graph": graph,
        "node_definitions": serialize_definitions(stage=builder_stage),
        "palette": palette,
        "is_debug": settings.DEBUG,
        "builder_stage": builder_stage,
        # React builder needs tenant-wide scripts for Flow Script node selection.
        "flow_scripts": FlowScriptSerializer.for_tenant(flow.tenant),
        "api_endpoints": _flow_api_endpoints(flow),
    }

    return context


@login_required
@never_cache
def flow_builder(request, flow_id):
    """
    Legacy builder entrypoint.

    The project has migrated to the React-based builder. Keep this URL for
    backwards compatibility and redirect callers to the React experience.
    """
    target = reverse("flows:builder_react", args=[flow_id])
    if request.headers.get("HX-Request"):
        resp = HttpResponse("", status=204)
        resp["HX-Redirect"] = target
        return resp
    return HttpResponseRedirect(target)


@login_required
@never_cache
def flow_builder_react(request: HttpRequest, flow_id):
    flow = get_object_or_404(Flow, id=flow_id)

    version = flow.versions.order_by("-created_at").first()
    available_webhooks = _available_webhooks_for_flow(flow)
    context = _flow_builder_page_context(request, flow, version, available_webhooks)

    template_name = "flows/flow_builder_react.html"

    if request.headers.get("HX-Request"):
        return render(request, template_name, context)

    context["partial_template"] = template_name
    return render(request, "layout.html", context)


@login_required
@require_http_methods(["GET"])
def flow_available_webhooks(request: HttpRequest, flow_id):
    flow = get_object_or_404(Flow, id=flow_id)
    webhooks = _available_webhooks_for_flow(flow)
    return JsonResponse({"webhooks": webhooks})


def flow_export(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id)
    version = flow.versions.order_by("-created_at").first()
    data = json.dumps(version.graph, indent=2)
    resp = HttpResponse(data, content_type="application/json")
    fname = f'{flow.name.lower().replace(" ","_")}_{version.label.replace(" ","_")}.json'
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp


@require_http_methods(["POST"])
def flow_import(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id)
    up = request.FILES.get("file")
    if not up:
        return HttpResponseBadRequest("file required")
    try:
        graph = json.load(up)
    except Exception:
        return HttpResponseBadRequest("invalid json")
    try:
        validated = validate_graph_payload(graph)
    except GraphValidationError as exc:
        return HttpResponseBadRequest(json.dumps({"errors": exc.errors()}))
    # Update existing draft or create new one
    last = flow.versions.order_by("-created_at").first()
    if last and not getattr(last, "is_editable", False):
        return HttpResponseForbidden(
            "This flow version is locked (published/archived). Create a draft version before importing."
        )
    if last and getattr(last, "is_editable", False):
        last.graph = validated.as_dict()
        last.save(update_fields=["graph", "updated_at"])
    else:
        next_version = (flow.versions.aggregate(Max("version")).get("version__max") or 0) + 1
        FlowVersion.objects.create(
            flow=flow,
            tenant=flow.tenant,
            version=next_version,
            status=FlowVersionStatus.DRAFT,
            graph=validated.as_dict(),
        )
    messages.success(request, "Graph imported.")
    return HttpResponseRedirect(reverse("flows:builder_react", args=[flow.id]))


@require_http_methods(["POST"])
def flow_toggle_active(request, flow_id):
    flow = get_object_or_404(Flow, id=flow_id)
    enable = not flow.is_enabled

    if enable:
        try:
            definition = compile_published_version(flow)
        except FlowCompilationError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("flows:list"))

        flow.status = "active"
        flow.save(update_fields=["status"])
        register_definition(flow, definition)
        messages.success(request, "Flow enabled")
    else:
        flow.status = "inactive"
        flow.save(update_fields=["status"])
        unregister_flow(flow)
        messages.info(request, "Flow disabled")

    return HttpResponseRedirect(reverse("flows:list"))


def _load_graph_from_request(request: HttpRequest) -> Dict[str, Any]:
    # Soporta JSON en body o campo POST 'graph'
    if request.content_type and "application/json" in request.content_type:
        raw = request.body.decode("utf-8") or "{}"
        data = json.loads(raw)

        # permitir { "graph": {...} } o el grafo directo
        return data["graph"] if isinstance(data, dict) and "graph" in data else data
    # fallback form
    raw = request.POST.get("graph") or "{}"
    return json.loads(raw)


def _graph_model_to_dict(graph_model: Any) -> Dict[str, Any]:
    """Convert the Pydantic graph model returned by :func:`normalize_graph` into a plain dict."""

    if hasattr(graph_model, "model_dump"):
        data = graph_model.model_dump(mode="python")
    else:  # pragma: no cover - compatibility fallback
        data = graph_model

    for node in data.get("nodes", []):
        ports = node.get("ports") or {}
        for side, entries in list(ports.items()):
            normalised: list[Dict[str, Any]] = []
            for entry in entries or []:
                if isinstance(entry, dict):
                    schema = entry.get("schema")
                    clone = {
                        "name": entry.get("name"),
                        "schema": deepcopy(schema) if schema else None,
                        "description": entry.get("description"),
                    }
                    preview = entry.get("schema_preview")
                    if preview:
                        clone["schema_preview"] = preview
                    elif schema:
                        clone["schema_preview"] = json.dumps(
                            schema, ensure_ascii=False, indent=2
                        )
                    normalised.append(clone)
                else:  # pragma: no cover - compatibility path
                    schema = getattr(entry, "schema", None)
                    preview = getattr(entry, "schema_preview", None)
                    clone = {
                        "name": getattr(entry, "name", None),
                        "schema": deepcopy(schema) if schema else None,
                        "description": getattr(entry, "description", None),
                    }
                    if preview:
                        clone["schema_preview"] = preview
                    elif schema:
                        clone["schema_preview"] = json.dumps(
                            schema, ensure_ascii=False, indent=2
                        )
                    normalised.append(clone)
            ports[side] = normalised
    return data


def _format_preview_entry_html(index: int, entry: Dict[str, Any]) -> str:
    name = entry.get("name") or entry.get("node_id") or "Unnamed"
    started = entry.get("started_at") or ""
    finished = entry.get("finished_at") or ""
    input_payload = entry.get("input", {})
    output_payload = entry.get("output", {})
    success_flag = None
    if isinstance(output_payload, dict) and "success" in output_payload:
        success_flag = output_payload.get("success")
    if success_flag is False and not output_payload.get("error"):
        output_payload = {**output_payload, "error": "Unknown error"}
    input_dump = html.escape(json.dumps(input_payload, indent=2, ensure_ascii=False))
    output_dump = html.escape(json.dumps(output_payload, indent=2, ensure_ascii=False))

    status_badge = ""
    if success_flag is True:
        status_badge = "<span class='badge text-bg-success ms-2'>Success</span>"
    elif success_flag is False:
        status_badge = "<span class='badge text-bg-danger ms-2'>Failed</span>"

    body = [
        "<div id='preview-log' hx-swap-oob='beforeend' class='preview-entry border-bottom pb-2 mb-2'>",
        "  <div class='d-flex justify-content-between align-items-center small fw-semibold text-secondary'>",
        f"    <span><span class='me-2 text-muted'>#{index}</span>{html.escape(str(name))}{status_badge}</span>",
        f"    <span class='text-muted'>{html.escape(str(started))} → {html.escape(str(finished))}</span>",
        "  </div>",
        "  <div class='small text-secondary mt-2'>Input</div>",
        f"  <pre class='bg-body-tertiary rounded p-2 small mb-2'>{input_dump}</pre>",
        "  <div class='small text-secondary'>Output</div>",
        f"  <pre class='bg-body-tertiary rounded p-2 small mb-0'>{output_dump}</pre>",
        "</div>",
    ]
    return "\n".join(body)


def _save_draft_version(
    flow: Flow,
    graph: Dict[str, Any],
    *,
    config_schema: dict | None = None,
    config_values: dict | None = None,
) -> FlowVersion:
    """Save a draft version of the flow graph."""
    # Only editable versions (draft/testing) may be modified via the builder.
    # If no editable version exists, the flow is effectively locked: callers must
    # explicitly create a new draft (e.g. by cloning a published version) before saving.
    latest_draft = (
        flow.versions.filter(status__in=[FlowVersionStatus.DRAFT, FlowVersionStatus.TESTING])
        .order_by("-created_at")
        .first()
    )

    if latest_draft:
        latest_draft.graph = graph
        if config_schema is not None:
            latest_draft.config_schema = config_schema
        if config_values is not None:
            latest_draft.config_values = config_values
        update_fields = ["graph", "updated_at"]
        if config_schema is not None:
            update_fields.append("config_schema")
        if config_values is not None:
            update_fields.append("config_values")
        latest_draft.save(update_fields=update_fields)
        return latest_draft

    # Bootstrap: allow creating the very first draft version for flows without any versions yet.
    if not flow.versions.exists():
        return FlowVersion.objects.create(
            flow=flow,
            tenant=flow.tenant,
            version=1,
            status=FlowVersionStatus.DRAFT,
            graph=graph,
            config_schema=config_schema or {},
            config_values=config_values or {},
        )

    raise PermissionError(
        "No editable flow version exists (flow is locked). Create a draft version before saving."
    )


def _preview_summary_html(execution: FlowExecution) -> str:
    status = execution.status.capitalize()
    duration = execution.duration_ms or 0
    context_payload = execution.output_data or {}
    failures = context_payload.get("$tool_failures") if isinstance(context_payload, dict) else []
    failures = failures or []

    summary_parts = [
        "<div id='preview-log' hx-swap-oob='beforeend' class='preview-summary small text-muted'>",
        f"<strong>Status:</strong> {html.escape(status)} · <strong>Duration:</strong> {duration} ms",
    ]

    if failures:
        summary_parts.append(f" · <strong>Tool failures:</strong> {len(failures)}")

    summary_parts.append("</div>")

    if failures:
        failure_dump = html.escape(json.dumps(failures, indent=2, ensure_ascii=False))
        summary_parts.extend(
            [
                "<div id='preview-log' hx-swap-oob='beforeend' class='preview-summary small text-danger mt-2'>",
                "<strong>Tool failure details</strong>",
                "</div>",
                "<div id='preview-log' hx-swap-oob='beforeend' class='preview-summary'>",
                f"<pre class='bg-body-tertiary rounded p-2 small mb-0'>{failure_dump}</pre>",
                "</div>",
            ]
        )

    return "".join(summary_parts)


@require_http_methods(["POST"])
def save(request: HttpRequest, flow_id: str):
    flow = get_object_or_404(Flow, id=flow_id)
    raw_graph = _load_graph_from_request(request)
    try:
        graph_model = normalize_graph(raw_graph)
    except Exception as exc:
        return HttpResponseBadRequest(str(exc))
    graph = _graph_model_to_dict(graph_model)

    # Internal contract validation (Normalize + sandboxed expressions over ctx.*).
    try:
        from flows.core.internal_contract import validate_flow_internal_contract
        validate_flow_internal_contract(graph or {})
    except Exception as exc:
        return HttpResponseBadRequest(str(exc))

    try:
        version = _save_draft_version(flow, graph)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    response = render(
        request,
        "flows/partials/_toast_oob.html",
        {"level": "success", "message": "Draft saved"},
        content_type="text/html",
        status=204,
    )
    response["HX-Trigger"] = json.dumps(
        {
            "flow-saved": {
                "version": version.version_label,
                "version_id": str(version.id),
                "major": version.version,  # Backward compat
                "minor": 0,  # Backward compat
                "is_published": version.is_published,
                "saved_at": now().isoformat(),
            }
        }
    )
    return response


@require_http_methods(["POST"])
def publish(request: HttpRequest, flow_id: str):
    flow = get_object_or_404(Flow, id=flow_id)
    latest = flow.versions.order_by("-created_at").first()
    if latest and not getattr(latest, "is_editable", False):
        return HttpResponseForbidden(
            "This flow version is locked (published/archived). Create a draft version to publish changes."
        )
    raw_graph = _load_graph_from_request(request) if request.body else None

    try:
        published_version = _publish_flow_version(flow, raw_graph)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    except FlowCompilationError as exc:
        return HttpResponseBadRequest(str(exc))

    response = render(
        request,
        "flows/partials/_toast_oob.html",
        {"level": "primary", "message": "Flow published"},
        content_type="text/html",
        status=204,
    )
    response["HX-Trigger"] = json.dumps(
        {
            "flow-published": {
                "version": published_version.version_label,
                "version_id": str(published_version.id),
                "major": published_version.version,  # Backward compat
                "minor": 0,  # Backward compat
                "is_published": True,
                "flow_status": flow.status,
            }
        }
    )
    return response


def _trigger_manual_run(flow: Flow, payload: dict[str, Any] | None):
    payload = payload if isinstance(payload, dict) else {}
    result = trigger_manual_flow_helper(str(flow.id), payload)
    detail: Dict[str, Any] = {
        "flow_id": str(flow.id),
        "triggered": bool(result.get("triggered")),
        "reason": result.get("reason"),
        "trigger_key": result.get("trigger_key"),
        "canonical_key": result.get("canonical_key"),
    }
    if detail["triggered"]:
        execution = (
            FlowExecution.objects.filter(flow=flow, trigger_source="manual")
            .order_by("-started_at")
            .first()
        )
        if execution:
            detail["execution_id"] = str(execution.id)

    reason = detail.get("reason")
    if detail["triggered"]:
        level = "primary"
        message = _("Manual flow run started.")
    elif reason == "disabled":
        level = "warning"
        message = _("Flow is disabled and was not triggered.")
    elif reason == "not_registered":
        level = "danger"
        message = _("Flow is not registered for manual execution.")
    else:
        level = "danger"
        message = _("Unable to start manual run.")
    return detail, level, message


@login_required
@require_http_methods(["POST"])
def manual_run(request: HttpRequest, flow_id: str):
    """Trigger a manual execution for a published flow."""

    flow = get_object_or_404(Flow, id=flow_id)
    body = _json_body(request)
    payload = body.get("payload") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        payload = {}

    detail, level, message = _trigger_manual_run(flow, payload)

    response = render(
        request,
        "flows/partials/_toast_oob.html",
        {"level": level, "message": message},
        content_type="text/html",
        status=200,
    )
    response["HX-Trigger"] = json.dumps({"flow-manual-run": detail})
    return response


def _has_webhook_trigger(graph: dict[str, Any]) -> dict[str, Any] | None:
    """Check if graph has a webhook trigger node and return its config if found."""
    nodes = graph.get("nodes", [])
    for node in nodes:
        if node.get("kind") == "trigger_webhook":
            return node.get("config", {})
    return None


def _get_webhook_url(webhook_id: str | None, tenant) -> str:
    """Build the full webhook URL from webhook ID using Django's reverse()."""
    if not webhook_id or not WebhookConfig:
        return ""
    try:
        webhook = WebhookConfig.objects.get(id=webhook_id, tenant=tenant)
        # Try to use the URL stored on the webhook config first
        if hasattr(webhook, 'url') and webhook.url:
            return webhook.url
        # Build URL using Django reverse
        from django.conf import settings
        try:
            path = reverse("generic_webhook_receiver", args=[str(webhook.id)])
        except Exception:
            path = f"/webhooks/{webhook.id}/"
        base_url = getattr(settings, 'SITE_URL', '') or getattr(settings, 'BASE_URL', '')
        if not base_url:
            base_url = "https://devcrm.moio.ai"
        return f"{base_url.rstrip('/')}{path}"
    except (WebhookConfig.DoesNotExist, Exception):
        return ""


def _execute_preview_run(
    flow: Flow,
    trigger_payload: dict[str, Any] | None,
    *,
    graph_payload: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> tuple[FlowExecution, str]:
    """
    Execute a preview run immediately with provided payload.
    
    Note: For flows with webhook triggers, use testing mode instead.
    Set the flow version to 'testing' status and trigger real webhooks
    to test with actual data in sandbox mode.
    """
    trigger_payload = trigger_payload if isinstance(trigger_payload, dict) else {}
    version = flow.versions.order_by("-created_at").first()

    if graph_payload is None:
        if not version:
            raise ValueError("No graph available to preview")
        graph_payload = version.graph

    try:
        graph_model = normalize_graph(graph_payload)
        graph_payload = _graph_model_to_dict(graph_model)
    except Exception as exc:
        raise ValueError(str(exc))

    run_identifier = run_id or str(uuid.uuid4())
    
    # Execute immediately with provided payload
    status_log = [{"status": "queued", "at": now().isoformat()}]
    exec_log = FlowExecution.objects.create(
        flow=flow,
        status="pending",
        input_data=trigger_payload,
        trigger_source="preview",
        execution_context={
            "preview_run_id": run_identifier,
            "graph_version": version.label if version else None,
            "status_log": status_log,
            "preview_active": False,
            "preview_started_at": now().isoformat(),
        },
    )

    preview_flow.apply_async(
        kwargs={
            "flow_id": str(flow.id),
            "run_id": run_identifier,
            "trigger_payload": trigger_payload,
            "graph_payload": graph_payload,
            "execution_id": str(exec_log.id),
        },
        queue=FLOWS_Q,
    )

    return exec_log, run_identifier


def _sync_webhook_flow_links(flow: Flow, graph: dict[str, Any]) -> None:
    """
    Sync ManyToMany relationship between WebhookConfig and Flow.
    
    For this specific flow:
    - Add it to any webhooks referenced in the graph's webhook triggers
    - Remove it from webhooks that were previously linked but are no longer in the graph
    
    This only affects the relationship for THIS flow, not other flows.
    """
    if WebhookConfig is None:
        return
    
    nodes = graph.get("nodes", [])
    current_webhook_ids = set()
    
    for node in nodes:
        if node.get("kind") == "trigger_webhook":
            config = node.get("config", {})
            webhook_id = config.get("webhook_id") or config.get("webhook_name")
            if webhook_id:
                current_webhook_ids.add(str(webhook_id))
    
    previous_webhook_ids = set(
        str(wh.id) for wh in flow.webhooks.all()
    )
    
    to_add = current_webhook_ids - previous_webhook_ids
    to_remove = previous_webhook_ids - current_webhook_ids
    
    if to_add:
        webhooks_to_link = WebhookConfig.objects.filter(
            id__in=to_add, 
            tenant=flow.tenant
        )
        for webhook in webhooks_to_link:
            webhook.linked_flows.add(flow)
            if webhook.handler_path != "flows.handlers.execute_flow_webhook":
                webhook.handler_path = "flows.handlers.execute_flow_webhook"
                webhook.save(update_fields=["handler_path"])
                logger.info(f"Set handler_path on webhook {webhook.id} for flow {flow.id}")
    
    if to_remove:
        webhooks_to_unlink = WebhookConfig.objects.filter(
            id__in=to_remove,
            tenant=flow.tenant
        )
        for webhook in webhooks_to_unlink:
            webhook.linked_flows.remove(flow)


def _publish_flow_version(
    flow: Flow, graph_payload: dict[str, Any] | None
) -> FlowVersion:
    """Publish a flow version - creates a new published FlowVersion and archives the previous one."""
    from django.utils.timezone import now as tz_now
    
    # Get the draft or latest version to use as source
    draft_version = (
        flow.versions.filter(status=FlowVersionStatus.DRAFT)
        .order_by("-created_at")
        .first()
    )

    cfg_schema: dict = {}
    cfg_values: dict = {}

    if graph_payload is not None:
        try:
            graph_model = normalize_graph(graph_payload)
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        graph = _graph_model_to_dict(graph_model)
        if isinstance(graph_payload, dict):
            raw_schema = graph_payload.get("config_schema") or graph_payload.get("configSchema") or {}
            raw_values = graph_payload.get("config_values") or graph_payload.get("configValues") or {}
            cfg_schema = raw_schema if isinstance(raw_schema, dict) else {}
            cfg_values = raw_values if isinstance(raw_values, dict) else {}
    else:
        fallback_version = draft_version or flow.versions.order_by("-created_at").first()
        if not fallback_version:
            raise ValueError("No graph available to publish")
        graph = fallback_version.graph
        cfg_schema = getattr(fallback_version, "config_schema", {}) or {}
        cfg_values = getattr(fallback_version, "config_values", {}) or {}

    # Strict deterministic contract validation (fail fast at publish-time).
    from flows.core.contract import validate_flow_contract
    validate_flow_contract(graph or {}, config_schema=cfg_schema, config_values=cfg_values)

    # Internal contract validation (Normalize + sandboxed expressions over ctx.*).
    from flows.core.internal_contract import validate_flow_internal_contract
    validate_flow_internal_contract(graph or {})

    # Archive existing published version if any
    existing_published = flow.published_version
    if existing_published:
        existing_published.status = FlowVersionStatus.ARCHIVED
        existing_published.save(update_fields=["status"])

    # Create new published version
    next_version = (flow.versions.aggregate(Max("version")).get("version__max") or 0) + 1
    
    published_version = FlowVersion.objects.create(
        flow=flow,
        tenant=flow.tenant,
        version=next_version,
        status=FlowVersionStatus.PUBLISHED,
        graph=graph,
        config_schema=cfg_schema,
        config_values=cfg_values,
        published_at=tz_now(),
    )

    # Update flow to point to new published version
    flow.published_version = published_version
    flow.status = "active"
    flow.save(update_fields=["status", "published_version"])
    
    # Register with the connector
    definition = compile_flow_graph(flow, graph, version=published_version)
    register_definition(flow, definition)
    
    _sync_webhook_flow_links(flow, graph)
    
    return published_version


@require_http_methods(["POST"])
def preview(request: HttpRequest, flow_id: str):
    """
    Inicia el preview (simulado). La UI se conecta por SSE a preview_stream.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON body")

    run_id = payload.get("run_id") or str(uuid.uuid4())
    trigger_payload = payload.get("payload") or {}
    graph_payload = payload.get("graph")

    flow = get_object_or_404(Flow, id=flow_id)

    try:
        exec_log, run_id = _execute_preview_run(
            flow,
            trigger_payload,
            graph_payload=graph_payload,
            run_id=run_id,
        )
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    ws_url = f"/ws/flows/{flow_id}/preview/stream/"

    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps(
        {
            "preview-started": {
                "run_id": run_id,
                "execution_id": str(exec_log.id),
                "ws_url": ws_url,
            }
        }
    )
    return response


def _sse_format(event: str | None, data: str) -> bytes:
    lines = []
    if event:
        lines.append(f"event: {event}")
    for line in data.splitlines() or [""]:
        lines.append(f"data: {line}")
    lines.append("")  # blank line
    return ("\n".join(lines) + "\n").encode("utf-8")


@require_http_methods(["GET"])
def preview_stream(request: HttpRequest, flow_id: str):
    """
    SSE streaming de logs HTML (puede ser OOB).
    """
    flow = get_object_or_404(Flow, id=flow_id)
    run_id = request.GET.get("run_id")

    def timeline_events() -> Iterable[bytes]:
        if not run_id:
            yield _sse_format(
                "message",
                "<div id='preview-log' hx-swap-oob='beforeend' class='text-danger'>Missing run id</div>",
            )
            return

        storage = get_storage()
        if storage is None:
            yield _sse_format(
                "message",
                "<div id='preview-log' hx-swap-oob='beforeend' class='text-warning'>Streaming backend unavailable.</div>",
            )
            return

        execution = (
            FlowExecution.objects.filter(
                flow=flow, execution_context__preview_run_id=run_id
            )
            .order_by("-started_at")
            .first()
        )

        if not execution:
            yield _sse_format(
                "message",
                "<div id='preview-log' hx-swap-oob='beforeend' class='text-warning'>Preview run not found.</div>",
            )
            return

        channel = f"preview-{flow.tenant_id or 'public'}-{run_id}"
        last_id = 0
        idle_loops = 0

        while True:
            try:
                events = storage.get_events(channel, last_id, limit=50)
            except EventDoesNotExist as exc:  # pragma: no cover - defensive
                last_id = getattr(exc, "current_id", 0)
                events = []

            new_events = [e for e in events if e.id != last_id]
            if new_events:
                idle_loops = 0
                for event in new_events:
                    last_id = event.id
                    yield sse_encode_event(
                        event.type,
                        event.data,
                        event_id=str(event.id),
                        json_encode=False,
                    )
                continue

            idle_loops += 1
            execution.refresh_from_db(fields=["execution_context"])
            preview_active = execution.execution_context.get("preview_active")
            if not preview_active and idle_loops > 2:
                break

            yield b"event: keep-alive\\ndata:\\n\\n"
            time.sleep(1)

    resp = StreamingHttpResponse(timeline_events(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    return resp


@api_view(["GET"])
def api_flow_node_definitions(request: Request):
    stage = request.GET.get("stage")
    if stage:
        stage = stage.strip().lower() or None
    if not stage:
        stage = "dev" if settings.DEBUG else "prod"

    definitions = serialize_definitions(stage=stage)
    return Response({"ok": True, "stage": stage, "definitions": definitions})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_crm_models(request: Request):
    """List CRM resource models available for the CRM CRUD flow node."""
    from crm.contracts import get_all_resources
    resources = [r.as_summary() for r in get_all_resources()]
    return Response({"ok": True, "models": resources})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_crm_model_detail(request: Request, slug: str):
    """Return CRM resource detail (ops + schemas) for the CRM CRUD flow node."""
    from crm.contracts import get_resource
    resource = get_resource(slug)
    if resource is None:
        return Response({"ok": False, "error": "Unknown CRM model"}, status=404)
    return Response({"ok": True, "model": resource.as_detail()})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def api_flow_list(request: Request):
    if request.method == "POST":
        serializer = FlowCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tenant = current_tenant.get() or getattr(request.user, "tenant", None)
        flow = serializer.save(tenant=tenant, created_by=getattr(request, "user", None))
        FlowVersion.objects.create(
            flow=flow,
            tenant=tenant,
            version=1,
            status=FlowVersionStatus.DRAFT,
            graph=_blank_graph(),
        )
        return Response(serializer.data, status=201)

    flows = (
        _flow_queryset_for_request(request)
        .select_related("tenant", "created_by", "published_version")
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=FlowVersion.objects.order_by("-created_at"),
                to_attr="version_list",
            )
        )
        .order_by("name")
    )
    tenant = getattr(request.user, "tenant", None)
    serialized = []
    for flow in flows:
        data = _serialize_flow(flow, include_versions=True)
        data["endpoints"] = _flow_api_endpoints(flow)
        serialized.append(data)
    return Response({"ok": True, "flows": serialized, "stats": _stats_for(tenant)})


@csrf_exempt
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def api_flow_detail(request: Request, flow_id: str):
    flow = _get_flow_for_request(request, flow_id)

    if request.method == "DELETE":
        is_active = flow.published_version_id is not None and flow.status == "active"
        if is_active:
            return Response(
                {"ok": False, "error": "Cannot delete an active flow. Deactivate or archive it first (toggle-active or set status to archived)."},
                status=400,
            )
        flow.delete()
        return Response({"ok": True, "message": "Flow deleted."}, status=200)

    if request.method == "PATCH":
        with transaction.atomic():
            flow_locked = Flow.objects.select_for_update().get(pk=flow.pk)
            serializer = FlowCreateSerializer(
                flow_locked, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response({"ok": True, "flow": _serialize_flow(flow_locked, include_versions=True)})

    version = flow.versions.order_by("-created_at").first()
    available_webhooks = _available_webhooks_for_flow(flow)
    context = _flow_builder_page_context(request, flow, version, available_webhooks)
    node_definitions = context["node_definitions"]
    palette_payload: list[dict[str, Any]] = []
    for section in context["palette"]:
        items: list[dict[str, Any]] = []
        for entry in section.get("items", []):
            serialized = node_definitions.get(getattr(entry, "kind", "")) if isinstance(node_definitions, dict) else None
            if serialized:
                items.append(serialized)
            else:
                items.append(
                    {
                        "kind": getattr(entry, "kind", None),
                        "title": getattr(entry, "title", None),
                        "icon": getattr(entry, "icon", None),
                        "category": getattr(entry, "category", None),
                        "description": getattr(entry, "description", None),
                    }
                )
        palette_payload.append({"label": section.get("label"), "items": items})
    payload = {
        "ok": True,
        "flow": _serialize_flow(flow, include_versions=True),
        "graph": context["graph"],
        "node_definitions": node_definitions,
        "palette": palette_payload,
        "webhooks": context["available_webhooks"],
        "scripts": context["flow_scripts"],
        "builder_stage": context["builder_stage"],
        "api": context.get("api_endpoints", {}),
    }
    tenant = getattr(request.user, "tenant", None)
    payload["stats"] = _stats_for(tenant)
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_validate(request: Request, flow_id: str):
    _get_flow_for_request(request, flow_id)
    try:
        graph_payload = _load_graph_from_request(request)
    except json.JSONDecodeError:
        return Response({"ok": False, "error": "Invalid request body."}, status=400)

    try:
        graph = validate_graph_payload(graph_payload)
    except GraphValidationError as exc:
        return Response({"ok": False, "errors": exc.errors()}, status=400)
    except Exception:
        return Response({"ok": False, "error": "Validation failed."}, status=400)

    return Response({"ok": True, "graph": graph.as_dict()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_save(request: Request, flow_id: str):
    """Save flow graph. 4xx from impl; unhandled exceptions → global API exception handler (500 + error_id)."""
    try:
        return _api_flow_save_impl(request, flow_id)
    except Http404:
        return Response({"ok": False, "error": "Flow not found."}, status=404)


def _api_flow_save_impl(request: Request, flow_id: str) -> Response:
    """Inner save logic. Returns 4xx Response for known errors; unhandled exceptions propagate to global handler."""
    flow = _get_flow_for_request(request, flow_id)

    try:
        raw_graph = _load_graph_from_request(request)
    except json.JSONDecodeError:
        return Response({"ok": False, "error": "Invalid JSON in request body."}, status=400)
    except Exception as exc:
        logger.warning("api_flow_save: load graph failed: %s", exc, exc_info=True)
        return Response({"ok": False, "error": "Could not read graph from request."}, status=400)

    expected_version_id = None
    config_schema = None
    config_values = None
    if isinstance(raw_graph, dict):
        expected_version_id = raw_graph.get("expected_version_id") or raw_graph.get("meta", {}).get("expected_version_id")
        config_schema = raw_graph.get("config_schema") or raw_graph.get("configSchema")
        config_values = raw_graph.get("config_values") or raw_graph.get("configValues")

    try:
        graph_model = normalize_graph(raw_graph)
    except ValueError:
        return Response({"ok": False, "error": "Graph validation failed."}, status=400)
    except Exception as exc:
        logger.warning("api_flow_save: normalize_graph failed: %s", exc, exc_info=True)
        return Response({"ok": False, "error": "Graph validation failed."}, status=400)

    try:
        graph = _graph_model_to_dict(graph_model)
    except Exception as exc:
        logger.warning("api_flow_save: graph_model_to_dict failed: %s", exc, exc_info=True)
        return Response({"ok": False, "error": "Could not process graph."}, status=400)

    try:
        with transaction.atomic():
            flow_locked = Flow.objects.select_for_update().get(pk=flow.pk)
            editable_version = (
                flow_locked.versions.filter(
                    status__in=[FlowVersionStatus.DRAFT, FlowVersionStatus.TESTING]
                )
                .order_by("-created_at")
                .first()
            )
            if not editable_version and flow_locked.versions.exists():
                return Response(
                    {
                        "ok": False,
                        "error": "This flow version is locked (published/archived). Create a draft version to edit.",
                    },
                    status=403,
                )
            _check_version_conflict(flow_locked, expected_version_id)
            version = _save_draft_version(
                flow_locked,
                graph,
                config_schema=config_schema if isinstance(config_schema, dict) else None,
                config_values=config_values if isinstance(config_values, dict) else None,
            )
            _sync_webhook_flow_links(flow_locked, graph)
    except VersionConflictError as exc:
        return _version_conflict_response(exc)
    except PermissionError:
        return Response({"ok": False, "error": "Permission denied."}, status=403)
    except Flow.DoesNotExist:
        return Response({"ok": False, "error": "Flow not found."}, status=404)
    # Any other exception propagates → global API exception handler (500 JSON + error_id)

    return Response({"ok": True, "version": _serialize_flow_version(version)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_preview(request: Request, flow_id: str):
    """
    Execute a preview run with provided payload.
    
    For webhook-triggered flows, use testing mode instead:
    1. Arm the draft version (POST /arm/) to set status to 'testing'
    2. Send real webhook requests to test with actual data in sandbox mode
    3. Disarm when done (POST /disarm/) to return to draft status
    """
    flow = _get_flow_for_request(request, flow_id)
    body = _json_body(request)
    run_id = body.get("run_id") if isinstance(body, dict) else None
    trigger_payload = body.get("payload") if isinstance(body, dict) else {}
    graph_payload = body.get("graph") if isinstance(body, dict) else None

    run_identifier = run_id or str(uuid.uuid4())
    try:
        execution, run_identifier = _execute_preview_run(
            flow,
            trigger_payload,
            graph_payload=graph_payload,
            run_id=run_identifier,
        )
    except ValueError:
        return Response({"ok": False, "error": "Invalid preview request."}, status=400)

    ws_url = f"/ws/flows/{flow_id}/preview/stream/"
    
    status_code = 200 if execution.status == "success" else 202
    return Response(
        {
            "ok": execution.status == "success",
            "run_id": run_identifier,
            "execution": _serialize_execution(execution),
            "ws_url": ws_url,
        },
        status=status_code,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_preview_status(request: Request, flow_id: str, run_id: uuid.UUID):
    flow = _get_flow_for_request(request, flow_id)
    execution = (
        FlowExecution.objects.filter(
            flow=flow, execution_context__preview_run_id=str(run_id)
        )
        .order_by("-started_at")
        .first()
    )
    if not execution:
        return Response(
            {"ok": False, "error": "Preview run not found."}, status=404
        )
    return Response({"ok": True, "execution": _serialize_execution(execution)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_preview_arm(request: Request, flow_id: str, version_id: uuid.UUID):
    """Start testing mode for a draft version (FSM transition: draft -> testing)."""
    flow = _get_flow_for_request(request, flow_id)

    try:
        version = flow.versions.get(id=version_id)
    except FlowVersion.DoesNotExist:
        return Response({"ok": False, "error": "Version not found"}, status=404)

    from django.db import IntegrityError
    from viewflow.fsm import TransitionNotAllowed
    try:
        from pydantic import ValidationError as PydanticValidationError
    except ImportError:
        PydanticValidationError = ()

    if not version.is_draft:
        return Response(
            {"ok": False, "error": f"Cannot start testing from {version.status} status. Only drafts can be armed."},
            status=400
        )
    try:
        from flows.core.contract import validate_flow_contract, FlowContractError
        validate_flow_contract(
            version.graph or {},
            config_schema=getattr(version, "config_schema", {}) or {},
            config_values=getattr(version, "config_values", {}) or {},
        )
        from flows.core.internal_contract import (
            validate_flow_internal_contract,
            FlowInternalContractError,
        )
        validate_flow_internal_contract(version.graph or {})
        version.start_testing()
        version.save()
        _sync_webhook_flow_links(flow, version.graph)
    except PydanticValidationError:
        return Response({"ok": False, "error": "Graph validation failed."}, status=400)
    except TransitionNotAllowed:
        return Response({"ok": False, "error": "Cannot start testing mode. Only drafts can be tested."}, status=400)
    except IntegrityError:
        return Response({"ok": False, "error": "Another version is already in testing mode. Please disarm it first."}, status=409)
    except (FlowContractError, FlowInternalContractError):
        return Response({"ok": False, "error": "Flow contract validation failed."}, status=400)
    except Exception as e:
        logger.warning("api_flow_preview_arm failed: %s", e, exc_info=True)
        return Response({"ok": False, "error": "Failed to start testing mode."}, status=500)

    try:
        return Response({
            "ok": True,
            "version": _serialize_flow_version(version),
            "message": "Testing mode activated. This version will now receive matching events in sandbox mode.",
        })
    except Exception as e:
        logger.warning("api_flow_preview_arm: serialize response failed: %s", e, exc_info=True)
        return Response({"ok": False, "error": "Testing mode activated but response serialization failed."}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_preview_disarm(request: Request, flow_id: str, version_id: uuid.UUID):
    """Return testing version back to draft mode (FSM transition: testing -> draft)."""
    flow = _get_flow_for_request(request, flow_id)
    
    try:
        version = flow.versions.get(id=version_id)
    except FlowVersion.DoesNotExist:
        return Response({"ok": False, "error": "Version not found"}, status=404)
    
    from viewflow.fsm import TransitionNotAllowed
    
    if not version.is_testing:
        return Response(
            {"ok": False, "error": f"Cannot disarm a version in {version.status} status. Only testing versions can be disarmed."},
            status=400
        )
    try:
        version.back_to_design()
        version.save()
        # Remove webhook links when disarming (returning to draft)
        # Create empty graph dict to trigger removal of all linked webhooks
        empty_graph = {"nodes": []}
        _sync_webhook_flow_links(flow, empty_graph)
    except TransitionNotAllowed:
        return Response({"ok": False, "error": "Cannot return to draft mode. Only testing versions can be disarmed."}, status=400)
    except Exception:
        return Response({"ok": False, "error": "Failed to return to draft mode."}, status=500)
    
    return Response({
        "ok": True,
        "version": _serialize_flow_version(version),
        "message": "Testing mode deactivated. This version is now a draft again.",
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_new_version(request: Request, flow_id: str):
    """Create a new draft version by cloning the currently published version."""
    flow = _get_flow_for_request(request, flow_id)
    
    try:
        if flow.published_version:
            new_draft = flow.published_version.clone_as_draft(user=request.user)
            return Response({
                "ok": True,
                "version": _serialize_flow_version(new_draft),
                "message": f"Created new draft v{new_draft.version} from published version.",
            })
    
        # Check for published version
        published = flow.versions.filter(status=FlowVersionStatus.PUBLISHED).first()
        if published:
            new_draft = published.clone_as_draft(user=request.user)
            return Response({
                "ok": True,
                "version": _serialize_flow_version(new_draft),
                "message": f"Created new draft v{new_draft.version} from published version.",
            })
    except Exception as exc:
        # Return JSON so the frontend can show a meaningful message (instead of Django's HTML 500 page).
        return Response({"ok": False, "error": f"Failed to create new version: {exc}"}, status=500)
    
    return Response(
        {"ok": False, "error": "No published version to clone"},
        status=400
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_versions(request: Request, flow_id: str):
    """List all versions for a flow."""
    flow = _get_flow_for_request(request, flow_id)
    include_graph = request.query_params.get("include_graph", "").lower() == "true"
    status_filter = request.query_params.get("status")
    
    versions = flow.versions.order_by("-version", "-created_at")
    if status_filter:
        versions = versions.filter(status=status_filter)
    return Response({
        "ok": True,
        "versions": [_serialize_flow_version(v, include_graph=include_graph) for v in versions],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_version_detail(request: Request, flow_id: str, version_id: uuid.UUID):
    """Get a specific version with full graph data."""
    flow = _get_flow_for_request(request, flow_id)
    
    try:
        version = flow.versions.get(id=version_id)
    except FlowVersion.DoesNotExist:
        return Response({"ok": False, "error": "Version not found"}, status=404)
    
    return Response({
        "ok": True,
        "version": _serialize_flow_version(version, include_graph=True),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_toggle_active(request: Request, flow_id: str):
    """
    Toggle active status for a flow.
    
    With the new FlowVersion model, is_enabled is derived from published_version presence.
    This endpoint archives the current published version to deactivate.
    To activate, use the publish endpoint on a draft/testing version.
    """
    from django.db import IntegrityError
    from viewflow.fsm import TransitionNotAllowed
    
    flow = _get_flow_for_request(request, flow_id)
    
    # New model: is_enabled is derived from published_version presence
    if flow.published_version:
        # Deactivate: archive the published version
        try:
            flow.published_version.archive()
            flow.published_version.save()
            # Refresh flow after archiving
            flow.refresh_from_db()
            return Response({
                "ok": True,
                "flow": _serialize_flow(flow),
                "message": "Flow deactivated. No longer receives events.",
            })
        except TransitionNotAllowed:
            return Response({"ok": False, "error": "Cannot archive this version. Only published versions can be archived."}, status=400)
        except IntegrityError as e:
            return Response({"ok": False, "error": "Database constraint violation."}, status=400)
        except Exception as e:
            return Response({"ok": False, "error": "Failed to archive version."}, status=500)
    else:
        # No published version - cannot toggle off, already off
        latest_draft = flow.versions.filter(status=FlowVersionStatus.DRAFT).order_by("-version").first()
        if latest_draft:
            return Response({
                "ok": False,
                "error": "Flow is already inactive. Use the publish endpoint to publish a draft first.",
            }, status=400)
        return Response({
            "ok": False,
            "error": "No versions available. Create and publish a version to activate the flow.",
        }, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_version_publish(request: Request, flow_id: str, version_id: uuid.UUID):
    """Publish a draft or testing version. 4xx from impl; unhandled → global API exception handler (500 + error_id)."""
    try:
        return _api_flow_version_publish_impl(request, flow_id, version_id)
    except Http404:
        return Response({"ok": False, "error": "Flow or version not found."}, status=404)


def _api_flow_version_publish_impl(
    request: Request, flow_id: str, version_id: uuid.UUID
) -> Response:
    flow = _get_flow_for_request(request, flow_id)

    try:
        version = flow.versions.get(id=version_id)
    except FlowVersion.DoesNotExist:
        return Response({"ok": False, "error": "Version not found"}, status=404)

    from django.db import IntegrityError
    from viewflow.fsm import TransitionNotAllowed
    try:
        from pydantic import ValidationError as PydanticValidationError
    except ImportError:
        PydanticValidationError = ()

    if version.is_published or version.is_archived:
        return Response(
            {"ok": False, "error": f"Cannot publish a version in {version.status} status."},
            status=400
        )
    try:
        from flows.core.contract import validate_flow_contract, FlowContractError
        validate_flow_contract(
            version.graph or {},
            config_schema=getattr(version, "config_schema", {}) or {},
            config_values=getattr(version, "config_values", {}) or {},
        )
        from flows.core.internal_contract import (
            validate_flow_internal_contract,
            FlowInternalContractError,
        )
        validate_flow_internal_contract(version.graph or {})
        version.publish()
        version.save()
        flow.refresh_from_db()
    except PydanticValidationError:
        return Response({"ok": False, "error": "Graph validation failed."}, status=400)
    except (FlowContractError, FlowInternalContractError):
        return Response({"ok": False, "error": "Flow contract validation failed."}, status=400)
    except TransitionNotAllowed:
        return Response({"ok": False, "error": "Cannot publish this version. Only drafts or testing versions can be published."}, status=400)
    except IntegrityError:
        return Response({"ok": False, "error": "Another version is already published. Please archive it first."}, status=409)
    # Any other exception propagates → global API exception handler (500 JSON + error_id)

    return Response({
        "ok": True,
        "version": _serialize_flow_version(version),
        "flow": _serialize_flow(flow),
        "message": f"Version v{version.version} published. Flow is now active and receiving events.",
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_version_archive(request: Request, flow_id: str, version_id: uuid.UUID):
    """Archive a published version (FSM transition: published -> archived)."""
    flow = _get_flow_for_request(request, flow_id)
    
    # Try new FlowVersion
    try:
        version = flow.versions.get(id=version_id)
    except (FlowVersion.DoesNotExist, AttributeError):
        return Response({"ok": False, "error": "Version not found or not using new model"}, status=404)
    
    from viewflow.fsm import TransitionNotAllowed
    
    if not version.is_published:
        return Response(
            {"ok": False, "error": f"Cannot archive a version in {version.status} status. Only published versions can be archived."},
            status=400
        )
    
    try:
        version.archive()
        version.save()
        # Refresh flow to get updated published_version (should be None now)
        flow.refresh_from_db()
    except TransitionNotAllowed:
        return Response({"ok": False, "error": "Cannot archive this version. Only published versions can be archived."}, status=400)
    except Exception:
        return Response({"ok": False, "error": "Failed to archive version."}, status=500)
    
    return Response({
        "ok": True,
        "version": _serialize_flow_version(version),
        "flow": _serialize_flow(flow),
        "message": f"Version v{version.version} archived. Flow no longer receives events.",
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_flow_version_restore(request: Request, flow_id: str, version_id: uuid.UUID):
    """Restore an archived version to published (FSM transition: archived -> published)."""
    flow = _get_flow_for_request(request, flow_id)
    try:
        version = flow.versions.get(id=version_id)
    except FlowVersion.DoesNotExist:
        return Response({"ok": False, "error": "Version not found"}, status=404)
    from viewflow.fsm import TransitionNotAllowed
    if not version.is_archived:
        return Response(
            {"ok": False, "error": f"Cannot restore a version in {version.status} status. Only archived versions can be restored."},
            status=400,
        )
    try:
        version.restore()
        version.save()
        flow.refresh_from_db()
    except TransitionNotAllowed:
        return Response({"ok": False, "error": "Cannot restore this version. Only archived versions can be restored."}, status=400)
    except Exception as e:
        logger.warning("api_flow_version_restore failed: %s", e, exc_info=True)
        return Response({"ok": False, "error": "Failed to restore version."}, status=500)
    return Response({
        "ok": True,
        "version": _serialize_flow_version(version),
        "flow": _serialize_flow(flow),
        "message": f"Version v{version.version} restored to published. Flow is active again.",
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_executions(request: Request, flow_id: str):
    """List executions for a flow with pagination and filtering.
    
    Query Parameters:
        limit: Max results (default 50, max 100)
        offset: Pagination offset
        status: Filter by status (pending, running, success, failed, timeout)
        trigger_source: Filter by trigger source (webhook, event, schedule, manual, preview)
        execution_mode: Filter by execution mode (production, testing, preview)
    """
    flow = _get_flow_for_request(request, flow_id)
    
    limit = min(int(request.query_params.get("limit", 50)), 100)
    offset = int(request.query_params.get("offset", 0))
    status_filter = request.query_params.get("status")
    trigger_source = request.query_params.get("trigger_source")
    execution_mode = request.query_params.get("execution_mode")
    
    executions = FlowExecution.objects.filter(flow=flow).select_related("flow").order_by("-started_at")
    
    if status_filter:
        executions = executions.filter(status=status_filter)
    if trigger_source:
        executions = executions.filter(trigger_source=trigger_source)
    if execution_mode:
        executions = executions.filter(execution_context__execution_mode=execution_mode)
    
    total = executions.count()
    executions = executions[offset:offset + limit]
    
    return Response({
        "ok": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "executions": [_serialize_execution(e) for e in executions],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_execution_detail(request: Request, flow_id: str, execution_id: uuid.UUID):
    """Get detailed execution data including full timeline."""
    flow = _get_flow_for_request(request, flow_id)
    
    try:
        execution = FlowExecution.objects.get(id=execution_id, flow=flow)
    except FlowExecution.DoesNotExist:
        return Response({"ok": False, "error": "Execution not found"}, status=404)
    
    return Response({
        "ok": True,
        "execution": _serialize_execution(execution),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_flow_execution_stats(request: Request, flow_id: str):
    """
    Return execution stats for a single flow.

    Query params:
      - days: window size (default 7, max 365)
    """
    flow = _get_flow_for_request(request, flow_id)

    try:
        days = int(request.query_params.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, 365))

    since = now() - timedelta(days=days)

    all_qs = FlowExecution.objects.filter(flow=flow)
    recent_qs = all_qs.filter(started_at__gte=since)

    total_all_time = all_qs.count()
    total_window = recent_qs.count()

    by_status = {
        (row.get("status") or "unknown"): int(row.get("count") or 0)
        for row in recent_qs.values("status").annotate(count=Count("id"))
    }
    by_trigger_source = {
        (row.get("trigger_source") or "unknown"): int(row.get("count") or 0)
        for row in recent_qs.values("trigger_source").annotate(count=Count("id"))
    }

    durations = recent_qs.exclude(duration_ms__isnull=True).aggregate(avg=Avg("duration_ms"))
    avg_duration_ms = durations.get("avg")

    success_count = int(by_status.get("success", 0))
    success_rate = (success_count / total_window) if total_window else None

    latest_runs = [
        {
            "id": str(e.id),
            "status": e.status,
            "trigger_source": e.trigger_source,
            "duration_ms": e.duration_ms,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        }
        for e in recent_qs.order_by("-started_at")[:10]
    ]

    return Response(
        {
            "ok": True,
            "flow_id": str(flow.id),
            "window_days": days,
            "total_all_time": total_all_time,
            "total_window": total_window,
            "by_status": by_status,
            "by_trigger_source": by_trigger_source,
            "avg_duration_ms": avg_duration_ms,
            "success_rate": success_rate,
            "latest_runs": latest_runs,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_all_executions(request: Request):
    """List all flow executions across all flows for the tenant with pagination and filtering.
    
    Query Parameters:
        limit: Max results (default 50, max 100)
        offset: Pagination offset
        status: Filter by status (pending, running, success, failed, timeout)
        trigger_source: Filter by trigger source (webhook, event, schedule, manual, preview)
        execution_mode: Filter by execution mode (production, testing, preview)
        flow_id: Filter by specific flow ID
    
    Staff users can access all executions; regular users are scoped to their tenant.
    """
    is_staff = getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)
    tenant_id = getattr(request.user, "tenant_id", None)
    
    if not is_staff and not tenant_id:
        return Response({"ok": False, "error": "Access denied"}, status=403)
    
    limit = min(int(request.query_params.get("limit", 50)), 100)
    offset = int(request.query_params.get("offset", 0))
    status_filter = request.query_params.get("status")
    trigger_source = request.query_params.get("trigger_source")
    execution_mode = request.query_params.get("execution_mode")
    flow_id_filter = request.query_params.get("flow_id")
    
    executions = FlowExecution.objects.select_related("flow").order_by("-started_at")
    
    if not is_staff:
        executions = executions.filter(flow__tenant_id=tenant_id)
    
    if flow_id_filter:
        executions = executions.filter(flow_id=flow_id_filter)
    if status_filter:
        executions = executions.filter(status=status_filter)
    if trigger_source:
        executions = executions.filter(trigger_source=trigger_source)
    if execution_mode:
        executions = executions.filter(execution_context__execution_mode=execution_mode)
    
    total = executions.count()
    executions = executions[offset:offset + limit]
    
    return Response({
        "ok": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "executions": [_serialize_execution(e) for e in executions],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_running_executions(request: Request):
    """List all currently running flow executions for real-time monitoring.
    
    Returns executions with status 'running' or 'pending' across all flows
    for the tenant. Useful for monitoring dashboards and debugging.
    
    Query Parameters:
        execution_mode: Filter by execution mode (production, testing, preview)
        flow_id: Filter by specific flow ID
    
    Staff users can access all running executions; regular users are scoped to their tenant.
    """
    is_staff = getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)
    tenant_id = getattr(request.user, "tenant_id", None)
    
    if not is_staff and not tenant_id:
        return Response({"ok": False, "error": "Access denied"}, status=403)
    
    execution_mode = request.query_params.get("execution_mode")
    flow_id_filter = request.query_params.get("flow_id")
    
    executions = FlowExecution.objects.filter(
        status__in=["running", "pending"]
    ).select_related("flow").order_by("-started_at")
    
    if not is_staff:
        executions = executions.filter(flow__tenant_id=tenant_id)
    
    if flow_id_filter:
        executions = executions.filter(flow_id=flow_id_filter)
    if execution_mode:
        executions = executions.filter(execution_context__execution_mode=execution_mode)
    
    return Response({
        "ok": True,
        "count": executions.count(),
        "executions": [_serialize_execution(e) for e in executions],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_execution_messages(request: Request, execution_id: str):
    """Get WhatsApp message logs and delivery statuses for a flow execution.
    
    This endpoint returns all WaMessageLog entries linked to a specific
    FlowExecution, allowing you to track message delivery lifecycle
    (sent -> delivered -> read).
    
    Path Parameters:
        execution_id: UUID of the FlowExecution
    
    Returns:
        List of message logs with status history
    """
    is_staff = getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)
    tenant_id = getattr(request.user, "tenant_id", None)
    
    if not is_staff and not tenant_id:
        return Response({"ok": False, "error": "Access denied"}, status=403)
    
    try:
        execution = FlowExecution.objects.select_related("flow").get(id=execution_id)
    except FlowExecution.DoesNotExist:
        return Response({"ok": False, "error": "Execution not found"}, status=404)
    
    if not is_staff and execution.flow.tenant_id != tenant_id:
        return Response({"ok": False, "error": "Access denied"}, status=403)
    
    try:
        from chatbot.models.wa_message_log import WaMessageLog
        # Seed message IDs from outbound logs tied to this execution.
        seed_msg_ids = (
            WaMessageLog.objects.filter(flow_execution_id=execution_id)
            .exclude(msg_id__isnull=True)
            .values_list("msg_id", flat=True)
            .distinct()
        )

        if not seed_msg_ids:
            return Response({
                "ok": True,
                "execution_id": str(execution.id),
                "flow_id": str(execution.flow_id),
                "flow_name": execution.flow.name,
                "seed_msg_ids_count": 0,
                "threads": [],
            })

        # Fetch full lifecycle events for those msg_ids within the same tenant.
        logs = (
            WaMessageLog.objects.filter(
                tenant=execution.flow.tenant,
                msg_id__in=seed_msg_ids,
            )
            .order_by("timestamp", "created", "updated")
        )

        threads = {}
        for log in logs:
            msg_id = log.msg_id
            if not msg_id:
                continue
            thread = threads.setdefault(
                msg_id,
                {
                    "msg_id": msg_id,
                    "events": [],
                    "first_seen_at": None,
                    "last_seen_at": None,
                    "latest_status": None,
                },
            )

            created_at = log.timestamp or log.created or log.updated
            iso_created = created_at.isoformat() if created_at else None

            thread["events"].append({
                "id": log.pk,
                "msg_id": log.msg_id,
                "type": log.type,
                "status": log.status,
                "user_number": log.user_number,
                "recipient_id": log.recipient_id,
                "body": log.body,
                "api_response": log.api_response,
                "created": log.created.isoformat() if log.created else None,
                "updated": log.updated.isoformat() if log.updated else None,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            })

            # Update bounds and latest status
            if thread["first_seen_at"] is None or (created_at and iso_created < thread["first_seen_at"]):
                thread["first_seen_at"] = iso_created
            if thread["last_seen_at"] is None or (created_at and iso_created > thread["last_seen_at"]):
                thread["last_seen_at"] = iso_created
                if log.status:
                    thread["latest_status"] = log.status

        messages = sorted(threads.values(), key=lambda t: t.get("first_seen_at") or "")
        
        return Response({
            "ok": True,
            "execution_id": str(execution.id),
            "flow_id": str(execution.flow_id),
            "flow_name": execution.flow.name,
            "seed_msg_ids_count": len(seed_msg_ids),
            "threads": messages,
        })
        
    except ImportError:
        return Response({
            "ok": False,
            "error": "WaMessageLog model not available",
        }, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_whatsapp_logs_by_execution(request: Request):
    """
    Consolidated WhatsApp logs for a FlowExecution, grouped by msg_id.
    
    Query params:
        - execution_id (required): FlowExecution UUID
    
    Response:
        {
          "ok": true,
          "flow": {id, name},
          "execution": {id},
          "message_count": N,
          "messages": [
            {
              "msg_id": "...",
              "recipient": "...",
              "body": "...",
              "first_status": "...",
              "last_status": "...",
              "created": "...",
              "updated": "...",
              "events": [
                {"status": "...", "timestamp": "...", "api_response": {...}}
              ]
            }
          ]
        }
    """
    is_staff = getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)
    tenant_id = getattr(request.user, "tenant_id", None)
    
    execution_id = request.query_params.get("execution_id")
    if not execution_id:
        return Response({"ok": False, "error": "execution_id is required"}, status=400)
    
    try:
        execution = FlowExecution.objects.select_related("flow").get(id=execution_id)
    except FlowExecution.DoesNotExist:
        return Response({"ok": False, "error": "Execution not found"}, status=404)
    
    if not is_staff and execution.flow.tenant_id != tenant_id:
        return Response({"ok": False, "error": "Access denied"}, status=403)
    
    try:
        from chatbot.models.wa_message_log import WaMessageLog

        logs = (
            WaMessageLog.objects.filter(flow_execution_id=execution_id)
            .order_by("timestamp", "created", "updated")
        )

        grouped: dict[str, dict] = {}
        for log in logs:
            key = log.msg_id or str(log.pk)
            bucket = grouped.setdefault(
                key,
                {
                    "msg_id": key,
                    "recipient": log.recipient_id or log.user_number,
                    "body": log.body,
                    # Enrichment fields (kept optional for backwards compatibility)
                    "flow_execution_id": str(log.flow_execution_id) if log.flow_execution_id else None,
                    "contact_phone": log.user_number,
                    "contact_name": log.user_name,
                    # Legacy field name kept for clients
                    "events": [],
                    # New preferred field name (same payload as events)
                    "statuses": [],
                    "created": None,
                    "updated": None,
                },
            )

            if not bucket.get("flow_execution_id") and log.flow_execution_id:
                bucket["flow_execution_id"] = str(log.flow_execution_id)

            evt_dt = log.timestamp or log.created or log.updated
            iso = evt_dt.isoformat() if evt_dt else None
            date_str = evt_dt.date().isoformat() if evt_dt else None
            time_str = evt_dt.time().replace(microsecond=0).isoformat() if evt_dt else None

            status_evt = {
                "status": log.status,
                # keep legacy key for compatibility
                "timestamp": iso,
                # new, explicit key (same value as timestamp)
                "occurred_at": iso,
                "date": date_str,
                "time": time_str,
                "type": log.type,
                "api_response": log.api_response,
            }

            bucket["events"].append(status_evt)
            bucket["statuses"].append(status_evt)

            if iso:
                if bucket["created"] is None or iso < bucket["created"]:
                    bucket["created"] = iso
                if bucket["updated"] is None or iso > bucket["updated"]:
                    bucket["updated"] = iso

        # Best-effort enrich with CRM Contact info (exact phone/mobile match)
        numbers = {b.get("contact_phone") for b in grouped.values() if b.get("contact_phone")}
        if numbers:
            try:
                from crm.models import Contact  # local import to avoid heavy module-level deps
                from django.db.models import Q

                contacts = (
                    Contact.objects.filter(tenant=execution.flow.tenant)
                    .filter(Q(phone__in=numbers) | Q(mobile__in=numbers))
                    .only("id", "phone", "mobile", "display_name", "fullname", "whatsapp_name", "first_name", "last_name", "email")
                )
                by_number = {}
                for c in contacts:
                    if c.phone:
                        by_number[c.phone] = c
                    if c.mobile:
                        by_number[c.mobile] = c

                for bucket in grouped.values():
                    phone = bucket.get("contact_phone")
                    contact = by_number.get(phone) if phone else None
                    if contact:
                        name = (
                            getattr(contact, "display_name", None)
                            or getattr(contact, "fullname", None)
                            or getattr(contact, "whatsapp_name", None)
                            or f"{getattr(contact, 'first_name', '')} {getattr(contact, 'last_name', '')}".strip()
                        )
                        bucket["contact"] = {
                            "id": str(contact.pk),
                            "name": name or bucket.get("contact_name") or "",
                            "phone": contact.phone or contact.mobile or phone or "",
                            "email": getattr(contact, "email", None) or "",
                        }
                    else:
                        bucket["contact"] = {
                            "id": None,
                            "name": bucket.get("contact_name") or "",
                            "phone": phone or "",
                            "email": "",
                        }
            except Exception:
                # If Contact model/query fails, keep log-provided fields only.
                for bucket in grouped.values():
                    if "contact" not in bucket:
                        bucket["contact"] = {
                            "id": None,
                            "name": bucket.get("contact_name") or "",
                            "phone": bucket.get("contact_phone") or "",
                            "email": "",
                        }

        # Derive first/last status in chronological order
        for bucket in grouped.values():
            statuses = bucket.get("statuses") or []
            non_null = [s.get("status") for s in statuses if s.get("status")]
            if non_null:
                bucket["first_status"] = non_null[0]
                bucket["last_status"] = non_null[-1]
                bucket["latest_status"] = non_null[-1]
            else:
                bucket["first_status"] = None
                bucket["last_status"] = None
                bucket["latest_status"] = None

        messages = sorted(grouped.values(), key=lambda x: x.get("created") or "", reverse=True)

        return Response(
            {
                "ok": True,
                "flow": {"id": str(execution.flow_id), "name": execution.flow.name},
                "execution": {"id": str(execution.id)},
                "message_count": len(messages),
                "messages": messages,
            }
        )

    except ImportError:
        return Response({
            "ok": False,
            "error": "WaMessageLog model not available",
        }, status=500)


#
# NOTE: The legacy node off-canvas editor endpoints (`node_editor`, `node_update`)
# were used by the retired builder experience and have been removed.
#


# ---------- Script views ----------
DEFAULT_SCRIPT_CODE = textwrap.dedent(
    '''
    def main(params):
        """Entry point for the script."""
        log(f"Received params: {params}")
        # TODO: Replace with your business logic.
        return {"echo": params}
    '''
).strip()

DEFAULT_SCRIPT_PARAMS = {"sample": "value"}


@login_required
def script_list(request: HttpRequest):
    tenant = current_tenant.get()
    scripts = FlowScript.objects.all()
    if tenant:
        scripts = scripts.filter(tenant=tenant)
    scripts = scripts.order_by("-updated_at")
    return render(request, "flows/scripts/list.html", {"scripts": scripts})


def _ensure_script_for_request(script_id, tenant):
    queryset = FlowScript.objects.all()
    if tenant:
        queryset = queryset.filter(tenant=tenant)
    return get_object_or_404(queryset, id=script_id)


def _prepare_script_payload(
    payload: dict[str, Any], script: FlowScript | None = None
) -> tuple[str, str, str, dict[str, Any], str, dict[str, str], list[str]]:
    name = (payload.get("name") or (script.name if script else "")).strip()
    description = (
        payload.get("description") or (script.description if script else "")
    ).strip()
    code = payload.get("code")
    if not code and script and script.latest_version:
        code = script.latest_version.code
    if not code:
        code = DEFAULT_SCRIPT_CODE

    raw_params = payload.get("params")
    params_text = None
    if isinstance(raw_params, dict):
        params_text = json.dumps(raw_params, ensure_ascii=False)
    else:
        params_text = (
            payload.get("params_text")
            or payload.get("paramsText")
            or payload.get("raw_params")
        )
    if params_text is None and script and script.latest_version:
        params_text = _pretty_json(script.latest_version.parameters or {})
    params_text = params_text or ""

    errors, messages, params = validate_script_payload(
        name, description, code, params_text
    )
    if isinstance(raw_params, dict) and "params" not in errors:
        params = raw_params
    return name, description, code, params, params_text, errors, messages


@login_required
def script_builder(request):
    script_id = request.GET.get("script_id")
    try:
        script = FlowScript.objects.get(id=script_id)
    except FlowScript.DoesNotExist:
        script = None

    context = {"script": script}
    if request.headers.get("HX-Request") == "true":
        return render(request, "flows/scripts/builder.html", context)
    return render(request, "layout.html", {"partial_template": "flows/scripts/builder.html", **context})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_script_validate(request: Request):
    tenant = current_tenant.get() or getattr(getattr(request, "user", None), "tenant", None)
    content_type = request.content_type or ""
    payload: dict[str, Any]
    if content_type and "application/json" in content_type:
        payload = _json_body(request)
    else:
        payload = request.POST.dict()
    if not isinstance(payload, dict):
        payload = {}
    params_value = payload.get("params")
    if params_value is not None and not isinstance(params_value, dict):
        payload.setdefault("params_text", params_value)

    script_identifier = payload.get("script_id") or payload.get("id")
    script: FlowScript | None = None
    if script_identifier:
        try:
            script = _ensure_script_for_request(script_identifier, tenant)
        except Http404:
            return Response(
                {"ok": False, "errors": {"script": "Script not found."}}, status=404
            )

    name, description, code, params, params_text, errors, messages = _prepare_script_payload(
        payload, script
    )

    status_code = 200 if not errors else 400
    response_payload = {
        "ok": not errors,
        "errors": errors,
        "messages": messages,
        "params": params,
        "params_text": params_text,
        "name": name,
        "description": description,
        "code": code,
    }
    return Response(response_payload, status=status_code)


@login_required
@require_http_methods(["POST"])
def script_validate(request):
    payload = request.POST.dict()
    params_value = payload.get("params")
    if params_value is not None and not isinstance(params_value, dict):
        payload.setdefault("params_text", params_value)

    _name, _description, _code, _params, _params_text, errors, messages = _prepare_script_payload(
        payload
    )

    if not errors:
        messages = [*messages, _("Validation successful.")]

    context = {"errors": errors, "messages": messages}
    status_code = 200 if not errors else 400
    html = render_to_string("flows/partials/_validation_feedback.html", context)
    return HttpResponse(html, status=status_code)


@login_required
@require_http_methods(["POST"])
def script_save_draft(request):
    tenant = current_tenant.get() or getattr(getattr(request, "user", None), "tenant", None)

    content_type = request.content_type or ""
    is_json = "application/json" in content_type
    if is_json:
        payload: dict[str, Any] = _json_body(request)
    else:
        payload = request.POST.dict()
        if "params" in payload and not isinstance(payload["params"], dict):
            payload.setdefault("params_text", payload["params"])

    script_identifier = payload.get("script_id") or payload.get("id")
    script: FlowScript | None = None
    if script_identifier:
        try:
            script = _ensure_script_for_request(script_identifier, tenant)
        except Http404:
            return JsonResponse(
                {"ok": False, "errors": {"script": "Script not found."}}, status=404
            )

    name, description, code, params, _params_text, errors, messages = _prepare_script_payload(
        payload, script
    )
    notes = (payload.get("notes") or payload.get("notes_text") or "").strip()

    if errors:
        return JsonResponse({"ok": False, "errors": errors, "messages": messages}, status=400)

    if script is None:
        slug_value = _unique_script_slug(name, tenant)
        script = FlowScript.objects.create(
            tenant=tenant,
            name=name,
            slug=slug_value,
            description=description,
        )
        version_number = 1
    else:
        script.name = name
        script.description = description
        script.save(update_fields=["name", "description", "updated_at"])
        latest_version = script.latest_version
        version_number = (latest_version.version_number if latest_version else 0) + 1

    FlowScriptVersion.objects.create(
        script=script,
        tenant=script.tenant,
        flow=script.flow,
        version_number=version_number,
        code=code,
        parameters=params,
        notes=notes,
    )

    serialized = _serialize_script(script, tenant=tenant)
    response = JsonResponse(
        {"ok": True, "messages": messages, "script": serialized}
    )
    if request.headers.get("HX-Request") == "true":
        response["HX-Trigger"] = "script-saved"
    return response


@login_required
@require_http_methods(["POST"])
def script_publish(request):
    tenant = current_tenant.get() or getattr(getattr(request, "user", None), "tenant", None)

    content_type = request.content_type or ""
    is_json = "application/json" in content_type
    if is_json:
        payload: dict[str, Any] = _json_body(request)
    else:
        payload = request.POST.dict()
        if "params" in payload and not isinstance(payload["params"], dict):
            payload.setdefault("params_text", payload["params"])

    script_identifier = payload.get("script_id") or payload.get("id")
    if not script_identifier:
        return JsonResponse(
            {"ok": False, "errors": {"script": "Script identifier required."}},
            status=400,
        )

    try:
        script = _ensure_script_for_request(script_identifier, tenant)
    except Http404:
        return JsonResponse(
            {"ok": False, "errors": {"script": "Script not found."}}, status=404
        )

    name, description, code, params, _params_text, errors, messages = _prepare_script_payload(
        payload, script
    )
    notes = (payload.get("notes") or payload.get("notes_text") or "").strip()

    if errors:
        return JsonResponse({"ok": False, "errors": errors, "messages": messages}, status=400)

    if name and name != script.name:
        script.name = name
    if description != script.description:
        script.description = description
    script.save(update_fields=["name", "description", "updated_at"])

    version_identifier = payload.get("version_id") or payload.get("version")
    version_to_publish: FlowScriptVersion | None = None
    if version_identifier:
        version_to_publish = (
            script.versions.filter(id=version_identifier).first()
        )
        if version_to_publish is None:
            return JsonResponse(
                {
                    "ok": False,
                    "errors": {"version": "Version not found for this script."},
                },
                status=404,
            )
    else:
        version_to_publish = script.latest_version

    needs_new_version = False
    if version_to_publish is None:
        needs_new_version = True
    elif not version_identifier:
        if version_to_publish.is_published:
            needs_new_version = True
        elif version_to_publish.code != code or (version_to_publish.parameters or {}) != (params or {}):
            needs_new_version = True

    if needs_new_version:
        latest_version = script.latest_version
        next_version_number = (latest_version.version_number if latest_version else 0) + 1
        version_to_publish = FlowScriptVersion.objects.create(
            script=script,
            tenant=script.tenant,
            flow=script.flow,
            version_number=next_version_number,
            code=code,
            parameters=params,
            notes=notes,
        )
    else:
        fields_to_update: list[str] = []
        if version_to_publish.notes != notes:
            version_to_publish.notes = notes
            fields_to_update.append("notes")
        if fields_to_update:
            version_to_publish.save(update_fields=fields_to_update)

    version_to_publish.publish()

    serialized = _serialize_script(script, tenant=tenant)
    response = JsonResponse({"ok": True, "script": serialized})
    if request.headers.get("HX-Request") == "true":
        response["HX-Trigger"] = "script-published"
    return response


@login_required
@require_http_methods(["POST"])
def script_run(request):
    tenant = current_tenant.get() or getattr(getattr(request, "user", None), "tenant", None)

    content_type = request.content_type or ""
    is_json = "application/json" in content_type
    if is_json:
        payload: dict[str, Any] = _json_body(request)
    else:
        payload = request.POST.dict()
        if "params" in payload and not isinstance(payload["params"], dict):
            payload.setdefault("params_text", payload["params"])

    script_identifier = payload.get("script_id") or payload.get("id")
    if not script_identifier:
        return JsonResponse(
            {"ok": False, "errors": {"script": "Script identifier required."}},
            status=400,
        )

    try:
        script = _ensure_script_for_request(script_identifier, tenant)
    except Http404:
        return JsonResponse(
            {"ok": False, "errors": {"script": "Script not found."}}, status=404
        )

    params: dict[str, Any] = {}
    raw_params = payload.get("params")
    if isinstance(raw_params, dict):
        params = raw_params
    else:
        params_text = payload.get("params_text") or payload.get("params") or "{}"
        if isinstance(params_text, str):
            try:
                params = json.loads(params_text)
            except json.JSONDecodeError:
                return JsonResponse(
                    {"ok": False, "errors": {"params": "Invalid JSON."}}, status=400
                )

    version_identifier = payload.get("version_id") or payload.get("version")
    version: FlowScriptVersion | None = None
    if version_identifier:
        version = script.versions.filter(id=version_identifier).first()
        if version is None:
            return JsonResponse(
                {
                    "ok": False,
                    "errors": {"version": "Version not found for this script."},
                },
                status=404,
            )
    else:
        version = script.published_version or script.latest_version

    if version is None:
        return JsonResponse(
            {"ok": False, "errors": {"version": "No version available to run."}},
            status=400,
        )

    run = FlowScriptRun.objects.create(
        tenant=script.tenant,
        flow=script.flow,
        script=script,
        version=version,
        input_payload=params,
        status=FlowScriptRun.STATUS_PENDING,
    )

    FlowScriptLog.objects.create(
        run=run,
        tenant=script.tenant,
        level=FlowScriptLog.LEVEL_INFO,
        message="Run queued.",
    )

    execute_script_run.apply_async(
        args=[str(run.id)],
        queue=FLOWS_Q,
    )

    html_feedback = render_to_string(
        "flows/partials/_validation_feedback.html",
        {"messages": [f"Run {str(run.id)[:8]} started. Streaming logs..."], "errors": {}},
    )
    response = JsonResponse({
        "run": {"id": str(run.id), "script_id": str(script.id)},
    }, status=202)
    response["HX-Trigger-After-Swap"] = "runStarted"
    response["HX-Retarget"] = "#script-feedback"
    response["HX-Reswap"] = "innerHTML"
    response.content = html_feedback
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def running_executions(request: Request) -> Response:
    """Get all running flow executions for the current tenant."""
    tenant = current_tenant.get()
    if not tenant:
        return Response({"error": "No tenant found"}, status=400)
    
    running = FlowExecution.objects.filter(
        flow__tenant=tenant,
        status="running"
    ).select_related("flow").values(
        "id", "flow__id", "flow__name", "status", "created_at", "trigger_source"
    ).order_by("-created_at")
    
    return Response({
        "executions": list(running)
    })


@login_required
def script_log_stream(request: HttpRequest, run_id: uuid.UUID):
    tenant = current_tenant.get()
    # EventSource uses GET only; accept script_id as query param so the stream URL works
    script_id = request.GET.get("script_id") or request.POST.get("script_id")
    if not script_id:
        return HttpResponse("script_id required (query or body)", status=400)
    script = _ensure_script_for_request(script_id, tenant)
    run = get_object_or_404(FlowScriptRun, id=run_id, script=script)

    def event_stream():
        last_timestamp = None
        while True:
            new_logs = FlowScriptLog.objects.filter(run=run)
            if last_timestamp:
                new_logs = new_logs.filter(created_at__gt=last_timestamp)
            for log_entry in new_logs.order_by("created_at"):
                last_timestamp = log_entry.created_at
                payload = {
                    "type": "log",
                    "level": log_entry.level,
                    "message": log_entry.message,
                    "details": log_entry.details or {},
                    "timestamp": log_entry.created_at.isoformat(),
                }
                yield f"data: {json.dumps(payload)}\n\n"

            run.refresh_from_db()
            if run.is_finished:
                payload = {
                    "type": "status",
                    "status": run.status,
                    "result": run.output_payload or {},
                    "error": run.error_payload or {},
                    "completed_at": run.completed_at.isoformat()
                    if run.completed_at
                    else None,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                break
            time.sleep(1)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    return response
