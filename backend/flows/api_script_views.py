"""API endpoints for managing and executing flow scripts."""

from __future__ import annotations

import json
from typing import Any

from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from flows.models import FlowScript, FlowScriptLog, FlowScriptRun, FlowScriptVersion
from flows.scripts import FlowScriptSerializer
from flows.scripts.param_hydration import resolve_datalab_param_refs
from flows.scripts.serializers import FlowScriptCreateSerializer
from flows.scripts.tasks import execute_script_run
from moio_platform.settings import FLOWS_Q
from portal.context_utils import current_tenant

from .views import (
    _ensure_script_for_request,
    _json_body,
    _prepare_script_payload,
    _serialize_run,
    _serialize_script,
)


def _tenant_from_request(request) -> Any:
    return current_tenant.get() or getattr(getattr(request, "user", None), "tenant", None)


def _parse_payload(request) -> dict[str, Any]:
    content_type = request.content_type or ""
    payload: dict[str, Any]
    if "application/json" in content_type:
        payload = _json_body(request)
    else:
        payload = request.POST.dict()
    if not isinstance(payload, dict):
        payload = {}
    params_value = payload.get("params")
    if params_value is not None and not isinstance(params_value, dict):
        payload.setdefault("params_text", params_value)
    return payload


def _prefetched_scripts_for(tenant):
    queryset = FlowScript.objects.all()
    if tenant:
        queryset = queryset.filter(tenant=tenant)
    return queryset.prefetch_related(
        Prefetch(
            "versions",
            queryset=FlowScriptVersion.objects.order_by("-version_number", "-created_at"),
        )
    ).order_by("-updated_at")


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def api_scripts(request):
    tenant = _tenant_from_request(request)

    if request.method == "GET":
        scripts = _prefetched_scripts_for(tenant)
        data = FlowScriptSerializer.serialize_many(scripts, include_versions=True)
        return Response({"scripts": data})

    serializer = FlowScriptCreateSerializer(
        data=request.data, context={"tenant": tenant}
    )
    try:
        serializer.is_valid(raise_exception=True)
    except DRFValidationError as exc:
        return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

    flow = serializer.validated_data.get("flow")
    serializer.save(tenant=tenant, flow=flow)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def api_script_detail(request, script_id):
    tenant = _tenant_from_request(request)
    script = get_object_or_404(_prefetched_scripts_for(tenant), id=script_id)

    if request.method == "GET":
        return Response({"script": _serialize_script(script, tenant=tenant)})

    payload = _parse_payload(request)
    name, description, code, params, _params_text, errors, messages = _prepare_script_payload(
        payload, script
    )
    if errors:
        return Response(
            {"ok": False, "errors": errors, "messages": messages},
            status=status.HTTP_400_BAD_REQUEST,
        )

    notes = (payload.get("notes") or payload.get("notes_text") or "").strip()

    with transaction.atomic():
        if name and name != script.name:
            script.name = name
        if description != script.description:
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

    script = _prefetched_scripts_for(tenant).get(id=script.id)
    serialized = _serialize_script(script, tenant=tenant)
    return Response({"ok": True, "script": serialized})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_script_execute(request):
    tenant = _tenant_from_request(request)
    payload = _parse_payload(request)

    script_identifier = payload.get("script_id") or payload.get("id")
    if not script_identifier:
        return Response(
            {"ok": False, "errors": {"script": "Script identifier required."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        script = _ensure_script_for_request(script_identifier, tenant)
    except Http404:
        return Response(
            {"ok": False, "errors": {"script": "Script not found."}},
            status=status.HTTP_404_NOT_FOUND,
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
                return Response(
                    {"ok": False, "errors": {"params": "Invalid JSON."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

    version_identifier = payload.get("version_id") or payload.get("version")
    version: FlowScriptVersion | None = None
    if version_identifier:
        version = script.versions.filter(id=version_identifier).first()
        if version is None:
            return Response(
                {"ok": False, "errors": {"version": "Version not found for this script."}},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        version = script.published_version or script.latest_version

    if version is None:
        return Response(
            {"ok": False, "errors": {"version": "No version available to run."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Resolve $datalab_resultset references in params before creating the run
    tenant_id = getattr(tenant, "id", None) if tenant else None
    if tenant_id and isinstance(params, dict):
        params = resolve_datalab_param_refs(params, str(tenant_id))

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

    return Response({"ok": True, "run": _serialize_run(run)}, status=status.HTTP_202_ACCEPTED)
