from __future__ import annotations

from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F, Func, IntegerField, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from moio_platform.api_schemas import STANDARD_ERRORS, Tags
from portal.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from security.authentication import ServiceJWTAuthentication

from .api_serializers import (
    RobotCreateSerializer,
    RobotEventSerializer,
    RobotMemoryCreateSerializer,
    RobotMemorySerializer,
    RobotRunSerializer,
    RobotSerializer,
    RobotSessionSerializer,
    RobotTriggerSerializer,
    UpdateIntentStateSerializer,
)
from .contracts import validate_instruction_payload
from .models import Robot, RobotEvent, RobotMemory, RobotRun, RobotSession
from .schedule_service import RobotScheduleService
from .tasks import cancel_robot_run, execute_robot_run
from .utils import is_within_operation_window


def _serialize_run(run: RobotRun) -> dict:
    session = run.session if run.session_id else None
    intent_state = session.intent_state if session else {}
    session_key = session.session_key if session else None
    return {
        "id": str(run.id),
        "robot_id": str(run.robot_id),
        "session_id": str(run.session_id) if run.session_id else None,
        "session_key": session_key,
        "status": run.status,
        "trigger_source": run.trigger_source,
        "trigger_payload": run.trigger_payload,
        "usage": run.usage,
        "execution_context": run.execution_context,
        "intent_state": intent_state,
        "output_data": run.output_data,
        "error_data": run.error_data,
        "cancel_requested_at": run.cancel_requested_at.isoformat() if run.cancel_requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _serialize_event(event: RobotEvent) -> dict:
    return {
        "id": str(event.id),
        "robot_id": str(event.robot_id),
        "run_id": str(event.run_id) if event.run_id else None,
        "session_id": str(event.session_id) if event.session_id else None,
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


def _parse_pagination_params(
    request,
    *,
    default_limit: int,
    default_offset: int,
    max_limit: int = 200,
) -> tuple[int, int] | Response:
    def _parse_int(name: str, default: int) -> int:
        raw = request.query_params.get(name, None)
        if raw is None or raw == "":
            return default
        return int(raw)

    try:
        limit = _parse_int("limit", default_limit)
        offset = _parse_int("offset", default_offset)
    except Exception:
        return Response(
            {"error": "invalid_pagination", "details": "limit and offset must be integers"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if limit < 1:
        return Response(
            {"error": "invalid_pagination", "details": "limit must be >= 1"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if limit > max_limit:
        limit = max_limit
    if offset < 0:
        return Response(
            {"error": "invalid_pagination", "details": "offset must be >= 0"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return limit, offset


@extend_schema_view(
    list=extend_schema(
        summary="List robots",
        tags=[Tags.ROBOTS],
        responses={200: OpenApiResponse(description="List robots"), **STANDARD_ERRORS},
    ),
    create=extend_schema(
        summary="Create robot",
        tags=[Tags.ROBOTS],
        request=RobotCreateSerializer,
        responses={201: RobotSerializer, **STANDARD_ERRORS},
    ),
    retrieve=extend_schema(
        summary="Get robot",
        tags=[Tags.ROBOTS],
        responses={200: RobotSerializer, **STANDARD_ERRORS},
    ),
    partial_update=extend_schema(
        summary="Update robot",
        tags=[Tags.ROBOTS],
        request=RobotCreateSerializer,
        responses={200: RobotSerializer, **STANDARD_ERRORS},
    ),
)
@method_decorator(csrf_exempt, name="dispatch")
class RobotViewSet(viewsets.ViewSet):
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]

    def _get_tenant(self, request):
        return getattr(request.user, "tenant", None)

    def _serialize_robot(self, robot: Robot) -> dict:
        return {
            "id": str(robot.id),
            "tenant_id": str(robot.tenant_id),
            "name": robot.name,
            "slug": robot.slug,
            "description": robot.description,
            "system_prompt": robot.system_prompt,
            "bootstrap_context": robot.bootstrap_context,
            "model_config": robot.model_config,
            "tools_config": robot.tools_config,
            "targets": robot.targets,
            "operation_window": robot.operation_window,
            "schedule": robot.schedule,
            "compaction_config": robot.compaction_config,
            "rate_limits": robot.rate_limits,
            "enabled": robot.enabled,
            "hard_timeout_seconds": robot.hard_timeout_seconds,
            "created_at": robot.created_at.isoformat(),
            "updated_at": robot.updated_at.isoformat(),
        }

    def _serialize_run(self, run: RobotRun) -> dict:
        return _serialize_run(run)

    def _serialize_event(self, event: RobotEvent) -> dict:
        return _serialize_event(event)

    def _serialize_session(self, session: RobotSession) -> dict:
        return {
            "id": str(session.id),
            "robot_id": str(session.robot_id),
            "session_key": session.session_key,
            "run_id": str(session.run_id) if session.run_id else None,
            "metadata": session.metadata,
            "intent_state": session.intent_state,
            "transcript_entries": len(session.transcript or []),
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }

    def _serialize_memory(self, memory: RobotMemory) -> dict:
        return {
            "id": str(memory.id),
            "robot_id": str(memory.robot_id),
            "session_id": str(memory.session_id) if memory.session_id else None,
            "kind": memory.kind,
            "payload": memory.payload,
            "created_at": memory.created_at.isoformat(),
            "expires_at": memory.expires_at.isoformat() if memory.expires_at else None,
        }

    def _is_inside_operation_window(self, robot: Robot) -> bool:
        window = robot.operation_window or {}
        start = window.get("start")
        end = window.get("end")
        if not start or not end:
            return True
        try:
            tz_name = window.get("tz") or "UTC"
            now_local = timezone.now().astimezone(ZoneInfo(tz_name))
            current_hhmm = now_local.strftime("%H:%M")
            return is_within_operation_window(start_hhmm=start, end_hhmm=end, current_hhmm=current_hhmm)
        except Exception:
            return True

    def _within_daily_run_guard(self, robot: Robot) -> bool:
        limits = robot.rate_limits or {}
        max_daily_runs = limits.get("max_daily_runs")
        if not max_daily_runs:
            return True
        day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        current_runs = RobotRun.objects.filter(robot=robot, started_at__gte=day_start).count()
        return current_runs < int(max_daily_runs)

    def list(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robots = Robot.objects.filter(tenant=tenant).order_by("-updated_at")
        return Response({"robots": [self._serialize_robot(r) for r in robots], "count": robots.count()})

    def create(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        data = request.data or {}
        name = (data.get("name") or "").strip()
        slug = (data.get("slug") or "").strip()
        if not name or not slug:
            return Response({"error": "name and slug are required"}, status=status.HTTP_400_BAD_REQUEST)

        robot = Robot(
            tenant=tenant,
            name=name,
            slug=slug,
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            bootstrap_context=data.get("bootstrap_context", {}),
            model_config=data.get("model_config", {}),
            tools_config=data.get("tools_config", {}),
            targets=data.get("targets", {}),
            operation_window=data.get("operation_window", {}),
            schedule=data.get("schedule", {}),
            compaction_config=data.get("compaction_config", {}),
            rate_limits=data.get("rate_limits", {}),
            enabled=data.get("enabled", True),
            hard_timeout_seconds=data.get("hard_timeout_seconds", 3600),
            created_by=request.user if request.user.is_authenticated else None,
        )
        try:
            with transaction.atomic():
                robot.full_clean()
                robot.save()
                RobotScheduleService.sync_robot(robot)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"robot": self._serialize_robot(robot)}, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant)
        return Response({"robot": self._serialize_robot(robot)})

    def partial_update(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant)

        data = request.data or {}
        updatable_fields = {
            "name",
            "slug",
            "description",
            "system_prompt",
            "bootstrap_context",
            "model_config",
            "tools_config",
            "targets",
            "operation_window",
            "schedule",
            "compaction_config",
            "rate_limits",
            "enabled",
            "hard_timeout_seconds",
        }
        for field in updatable_fields:
            if field in data:
                setattr(robot, field, data[field])
        try:
            with transaction.atomic():
                robot.full_clean()
                robot.save()
                RobotScheduleService.sync_robot(robot)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"robot": self._serialize_robot(robot)})

    @extend_schema(
        summary="Trigger robot run",
        tags=[Tags.ROBOTS],
        request=RobotTriggerSerializer,
        responses={202: RobotRunSerializer, **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="trigger")
    def trigger(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant, enabled=True)
        if not self._is_inside_operation_window(robot):
            return Response(
                {"error": "operation_window is closed; run not enqueued"},
                status=status.HTTP_409_CONFLICT,
            )
        if not self._within_daily_run_guard(robot):
            return Response(
                {"error": "max_daily_runs exceeded; run not enqueued"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            payload = validate_instruction_payload(request.data or {})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        session_key = (payload.get("session_key") or "").strip()
        if not session_key:
            session_key = f"manual:{timezone.now().strftime('%Y%m%d%H%M%S')}"

        try:
            session, _ = RobotSession.objects.get_or_create(
                robot=robot,
                session_key=session_key,
                defaults={"metadata": {"created_by": "api_trigger"}, "transcript": [], "intent_state": {}},
            )
        except ValidationError as exc:
            return Response({"error": "invalid_session_key", "details": exc.message_dict}, status=400)
        with transaction.atomic():
            run = RobotRun.objects.create(
                robot=robot,
                session=session,
                trigger_source=payload.get("trigger_source") or "manual",
                trigger_payload=payload,
                status=RobotRun.STATUS_PENDING,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.run_id = run.id
            session.save(update_fields=["run_id", "updated_at"])
            run_id = str(run.id)
            transaction.on_commit(lambda: execute_robot_run.apply_async(args=[run_id]))

        return Response({"run": self._serialize_run(run)}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        summary="List robot runs",
        tags=[Tags.ROBOTS],
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("offset", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiResponse(description="List robot runs"), **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["get"], url_path="runs")
    def runs(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant)
        parsed = _parse_pagination_params(request, default_limit=50, default_offset=0, max_limit=100)
        if isinstance(parsed, Response):
            return parsed
        limit, offset = parsed
        runs_qs = RobotRun.objects.filter(robot=robot).select_related("session").order_by("-started_at")
        total = runs_qs.count()
        runs = runs_qs[offset : offset + limit]
        return Response(
            {
                "runs": [self._serialize_run(r) for r in runs],
                "count": len(runs),
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    @extend_schema(
        summary="List robot sessions",
        tags=[Tags.ROBOTS],
        responses={200: OpenApiResponse(description="List robot sessions"), **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["get"], url_path="sessions")
    def sessions(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant)
        sessions = RobotSession.objects.filter(robot=robot).order_by("-updated_at")
        return Response(
            {
                "sessions": [self._serialize_session(s) for s in sessions],
                "count": sessions.count(),
            }
        )

    @extend_schema(
        summary="List robot events",
        tags=[Tags.ROBOTS],
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("offset", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: RobotEventSerializer(many=True), **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["get"], url_path="events")
    def events(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant)
        parsed = _parse_pagination_params(request, default_limit=100, default_offset=0, max_limit=500)
        if isinstance(parsed, Response):
            return parsed
        limit, offset = parsed
        events_qs = RobotEvent.objects.filter(robot=robot).order_by("-created_at")
        total = events_qs.count()
        events = events_qs[offset : offset + limit]
        return Response(
            {
                "events": [self._serialize_event(e) for e in events],
                "count": len(events),
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    @extend_schema(
        summary="Cancel run by robot",
        tags=[Tags.ROBOTS],
        responses={200: RobotRunSerializer, **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["post"], url_path=r"runs/(?P<run_id>[^/.]+)/cancel")
    def cancel_run(self, request, pk=None, run_id=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant)
        run = get_object_or_404(RobotRun.objects.select_related("session"), id=run_id, robot=robot)

        run.cancel_requested_at = timezone.now()
        with transaction.atomic():
            run.save(update_fields=["cancel_requested_at"])
            run_id_str = str(run.id)
            transaction.on_commit(lambda: cancel_robot_run.apply_async(args=[run_id_str]))
        return Response({"run": self._serialize_run(run), "message": "cancel_requested"})

    @extend_schema(
        summary="List or create robot memory",
        tags=[Tags.ROBOTS],
        request=RobotMemoryCreateSerializer,
        responses={
            200: OpenApiResponse(description="List robot memories"),
            201: RobotMemorySerializer,
            **STANDARD_ERRORS,
        },
    )
    @action(detail=True, methods=["get", "post"], url_path="memories")
    def memories(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        robot = get_object_or_404(Robot, id=pk, tenant=tenant)

        if request.method.lower() == "get":
            memories = RobotMemory.objects.filter(robot=robot).order_by("-created_at")
            return Response(
                {
                    "memories": [self._serialize_memory(m) for m in memories],
                    "count": memories.count(),
                }
            )

        data = request.data or {}
        session_id = data.get("session_id")
        session = None
        if session_id:
            session = get_object_or_404(RobotSession, id=session_id, robot=robot)
        memory = RobotMemory.objects.create(
            robot=robot,
            session=session,
            kind=data.get("kind") or "fact",
            payload=data.get("payload") or {},
            expires_at=parse_datetime(data.get("expires_at")) if data.get("expires_at") else None,
        )
        return Response({"memory": self._serialize_memory(memory)}, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Get backend contracts",
        tags=[Tags.ROBOTS],
        responses={200: OpenApiResponse(description="Instruction and LLM output contracts")},
    )
    @action(detail=False, methods=["get"], url_path="contracts")
    def contracts(self, request):
        return Response(
            {
                "instruction_payload": {
                    "instruction_schema_version": "int (default 1)",
                    "instruction": "string",
                    "objective_override": "object",
                    "queue_items": "array",
                    "constraints": "object",
                    "metadata": "object",
                    "session_key": "string (optional)",
                    "trigger_source": "string (optional)",
                },
                "llm_output": {
                    "assistant_message": "string (required)",
                    "tool_calls": "array (required)",
                    "plan_patch": "object|null (required)",
                    "stop_reason": "string (required)",
                },
            }
        )


@extend_schema_view(
    list=extend_schema(
        summary="List runs (tenant)",
        tags=[Tags.ROBOTS],
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("offset", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiResponse(description="List tenant robot runs"), **STANDARD_ERRORS},
    ),
    retrieve=extend_schema(
        summary="Get run",
        tags=[Tags.ROBOTS],
        responses={200: RobotRunSerializer, **STANDARD_ERRORS},
    ),
)
@method_decorator(csrf_exempt, name="dispatch")
class RobotRunViewSet(viewsets.ViewSet):
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]

    def _get_tenant(self, request):
        return getattr(request.user, "tenant", None)

    def _serialize_run(self, run: RobotRun) -> dict:
        return _serialize_run(run)

    def _serialize_event(self, event: RobotEvent) -> dict:
        return _serialize_event(event)

    def list(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        parsed = _parse_pagination_params(request, default_limit=50, default_offset=0, max_limit=100)
        if isinstance(parsed, Response):
            return parsed
        limit, offset = parsed
        runs_qs = RobotRun.objects.filter(robot__tenant=tenant).select_related("robot", "session").order_by("-started_at")
        total = runs_qs.count()
        runs = runs_qs[offset : offset + limit]
        return Response(
            {
                "runs": [self._serialize_run(r) for r in runs],
                "count": len(runs),
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    def retrieve(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        run = get_object_or_404(RobotRun.objects.select_related("session"), id=pk, robot__tenant=tenant)
        return Response({"run": self._serialize_run(run)})

    @extend_schema(
        summary="Cancel run",
        tags=[Tags.ROBOTS],
        responses={200: RobotRunSerializer, **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        run = get_object_or_404(RobotRun.objects.select_related("session"), id=pk, robot__tenant=tenant)
        run.cancel_requested_at = timezone.now()
        with transaction.atomic():
            run.save(update_fields=["cancel_requested_at"])
            run_id_str = str(run.id)
            transaction.on_commit(lambda: cancel_robot_run.apply_async(args=[run_id_str]))
        return Response({"run": self._serialize_run(run), "message": "cancel_requested"})

    @extend_schema(
        summary="List run events",
        tags=[Tags.ROBOTS],
        responses={200: RobotEventSerializer(many=True), **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["get"], url_path="events")
    def events(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        run = get_object_or_404(RobotRun.objects.select_related("robot"), id=pk, robot__tenant=tenant)
        events = RobotEvent.objects.filter(run=run).order_by("-created_at")
        return Response({"events": [self._serialize_event(e) for e in events], "count": events.count()})


@extend_schema_view(
    list=extend_schema(
        summary="List sessions (tenant)",
        tags=[Tags.ROBOTS],
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("offset", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiResponse(description="List robot sessions"), **STANDARD_ERRORS},
    ),
    retrieve=extend_schema(
        summary="Get session",
        tags=[Tags.ROBOTS],
        responses={200: RobotSessionSerializer, **STANDARD_ERRORS},
    ),
)
@method_decorator(csrf_exempt, name="dispatch")
class RobotSessionViewSet(viewsets.ViewSet):
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]

    def _get_tenant(self, request):
        return getattr(request.user, "tenant", None)

    def _transcript_entries_expr(self):
        if connection.vendor == "postgresql":
            fn = "jsonb_array_length"
        elif connection.vendor == "mysql":
            fn = "JSON_LENGTH"
        else:
            fn = "json_array_length"
        return Coalesce(
            Func(F("transcript"), function=fn, output_field=IntegerField()),
            Value(0),
        )

    def _serialize_session(self, session: RobotSession) -> dict:
        return {
            "id": str(session.id),
            "robot_id": str(session.robot_id),
            "session_key": session.session_key,
            "run_id": str(session.run_id) if session.run_id else None,
            "metadata": session.metadata,
            "intent_state": session.intent_state,
            "transcript": session.transcript,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }

    def _serialize_session_summary(self, session: RobotSession) -> dict:
        transcript_entries = getattr(session, "transcript_entries", None)
        if transcript_entries is None:
            transcript_entries = len(session.transcript or [])
        return {
            "id": str(session.id),
            "robot_id": str(session.robot_id),
            "session_key": session.session_key,
            "run_id": str(session.run_id) if session.run_id else None,
            "metadata": session.metadata,
            "intent_state": session.intent_state,
            "transcript_entries": transcript_entries,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }

    def list(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        sessions_qs = (
            RobotSession.objects.filter(robot__tenant=tenant)
            .select_related("robot")
            .defer("transcript")
            .annotate(transcript_entries=self._transcript_entries_expr())
            .order_by("-updated_at")
        )
        parsed = _parse_pagination_params(request, default_limit=50, default_offset=0, max_limit=100)
        if isinstance(parsed, Response):
            return parsed
        limit, offset = parsed
        total = sessions_qs.count()
        sessions = sessions_qs[offset : offset + limit]
        return Response(
            {
                "sessions": [self._serialize_session_summary(s) for s in sessions],
                "count": len(sessions),
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    def retrieve(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        session = get_object_or_404(RobotSession, id=pk, robot__tenant=tenant)
        return Response({"session": self._serialize_session(session)})

    @extend_schema(
        summary="Update session intent_state",
        tags=[Tags.ROBOTS],
        request=UpdateIntentStateSerializer,
        responses={200: RobotSessionSerializer, **STANDARD_ERRORS},
    )
    @action(detail=True, methods=["patch"], url_path="intent-state")
    def update_intent_state(self, request, pk=None):
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        session = get_object_or_404(RobotSession, id=pk, robot__tenant=tenant)
        intent_state = request.data.get("intent_state")
        if not isinstance(intent_state, dict):
            return Response({"error": "intent_state must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        session.intent_state = intent_state
        session.save(update_fields=["intent_state", "updated_at"])
        return Response({"session": self._serialize_session(session)})
