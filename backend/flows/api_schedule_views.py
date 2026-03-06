"""
API Views for FlowSchedule management.

Provides CRUD endpoints for flow schedules with Celery Beat sync.
"""

import logging
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from .models import Flow, FlowSchedule
from .core.schedule_service import ScheduleService
from moio_platform.api_schemas import Tags, STANDARD_ERRORS

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="Get flow schedule",
        description="Get the schedule for a flow (each flow has at most one schedule).",
        tags=[Tags.FLOW_SCHEDULES],
    ),
    create=extend_schema(
        summary="Create/update schedule",
        description="Create or update schedule. Fields: schedule_type (cron/interval/one_off), cron_expression, interval_seconds, run_at, timezone, is_active.",
        tags=[Tags.FLOW_SCHEDULES],
    ),
    retrieve=extend_schema(
        summary="Get schedule details",
        description="Get details of a specific schedule.",
        tags=[Tags.FLOW_SCHEDULES],
    ),
    update=extend_schema(
        summary="Update schedule",
        description="Update schedule configuration.",
        tags=[Tags.FLOW_SCHEDULES],
    ),
    destroy=extend_schema(
        summary="Delete schedule",
        description="Delete a schedule and remove from Celery Beat.",
        tags=[Tags.FLOW_SCHEDULES],
    ),
)
class FlowScheduleViewSet(ViewSet):
    """ViewSet for managing flow schedules with Celery Beat integration."""
    
    permission_classes = [IsAuthenticated]
    
    def _get_flow(self, request, flow_pk):
        """Get flow and verify tenant access."""
        tenant = getattr(request.user, 'tenant', None)
        if tenant:
            return get_object_or_404(Flow, pk=flow_pk, tenant=tenant)
        return get_object_or_404(Flow, pk=flow_pk)
    
    def _serialize_schedule(self, schedule):
        """Serialize a FlowSchedule to dict."""
        return {
            'id': str(schedule.id),
            'flow_id': str(schedule.flow_id),
            'schedule_type': schedule.schedule_type,
            'cron_expression': schedule.cron_expression or None,
            'interval_seconds': schedule.interval_seconds,
            'run_at': schedule.run_at.isoformat() if schedule.run_at else None,
            'timezone': schedule.timezone,
            'is_active': schedule.is_active,
            'next_run_at': schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            'last_run_at': schedule.last_run_at.isoformat() if schedule.last_run_at else None,
            'celery_task_name': schedule.celery_task_name or None,
            'created_at': schedule.created_at.isoformat(),
            'updated_at': schedule.updated_at.isoformat(),
        }
    
    def list(self, request, flow_pk=None):
        """List schedule for a flow (returns single schedule if exists)."""
        flow = self._get_flow(request, flow_pk)
        
        try:
            schedule = flow.schedule
            return Response({
                'schedule': self._serialize_schedule(schedule),
            })
        except FlowSchedule.DoesNotExist:
            return Response({
                'schedule': None,
            })
    
    def create(self, request, flow_pk=None):
        """Create a new schedule for a flow."""
        flow = self._get_flow(request, flow_pk)
        
        data = request.data
        schedule_type = data.get('schedule_type', FlowSchedule.SCHEDULE_TYPE_CRON)

        # Idempotent create (upsert): the editor/publish flows often POST blindly.
        # If a schedule already exists for this flow, update it instead of failing.
        existing = FlowSchedule.objects.filter(flow=flow).first()
        is_update = existing is not None
        schedule = existing or FlowSchedule(flow=flow, tenant=flow.tenant)

        schedule.schedule_type = schedule_type
        schedule.cron_expression = data.get('cron_expression', '') if schedule_type == FlowSchedule.SCHEDULE_TYPE_CRON else ''
        schedule.interval_seconds = data.get('interval_seconds') if schedule_type == FlowSchedule.SCHEDULE_TYPE_INTERVAL else None
        schedule.timezone = data.get('timezone', 'UTC')
        if 'is_active' in data:
            schedule.is_active = data.get('is_active', True)

        if schedule_type == FlowSchedule.SCHEDULE_TYPE_ONE_OFF and data.get('run_at'):
            from django.utils.dateparse import parse_datetime
            schedule.run_at = parse_datetime(data['run_at'])
        elif schedule_type != FlowSchedule.SCHEDULE_TYPE_ONE_OFF:
            schedule.run_at = None

        try:
            schedule.full_clean()
            schedule.save()
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'success': True,
                'message': 'Schedule updated successfully' if is_update else 'Schedule created successfully',
                'schedule': self._serialize_schedule(schedule),
            },
            status=status.HTTP_200_OK if is_update else status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, flow_pk=None, pk=None):
        """Get schedule details."""
        flow = self._get_flow(request, flow_pk)
        schedule = get_object_or_404(FlowSchedule, pk=pk, flow=flow)
        
        return Response({
            'schedule': self._serialize_schedule(schedule),
        })
    
    def update(self, request, flow_pk=None, pk=None):
        """Update a schedule."""
        flow = self._get_flow(request, flow_pk)
        schedule = get_object_or_404(FlowSchedule, pk=pk, flow=flow)
        
        data = request.data
        
        if 'schedule_type' in data:
            schedule.schedule_type = data['schedule_type']
        if 'cron_expression' in data:
            schedule.cron_expression = data['cron_expression']
        if 'interval_seconds' in data:
            schedule.interval_seconds = data['interval_seconds']
        if 'timezone' in data:
            schedule.timezone = data['timezone']
        if 'is_active' in data:
            schedule.is_active = data['is_active']
        if 'run_at' in data:
            from django.utils.dateparse import parse_datetime
            schedule.run_at = parse_datetime(data['run_at']) if data['run_at'] else None
        
        try:
            schedule.full_clean()
            schedule.save()
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'success': True,
            'message': 'Schedule updated successfully',
            'schedule': self._serialize_schedule(schedule),
        })
    
    def destroy(self, request, flow_pk=None, pk=None):
        """Delete a schedule."""
        flow = self._get_flow(request, flow_pk)
        schedule = get_object_or_404(FlowSchedule, pk=pk, flow=flow)
        
        schedule_id = str(schedule.id)
        schedule.delete()
        
        return Response({
            'success': True,
            'message': 'Schedule deleted successfully',
            'deleted_id': schedule_id,
        })
    
    @extend_schema(
        summary="Toggle schedule",
        description="Toggle the active state of a schedule.",
        tags=[Tags.FLOW_SCHEDULES],
        responses={200: OpenApiResponse(description="Schedule toggled successfully")},
    )
    @action(detail=True, methods=['post'])
    def toggle(self, request, flow_pk=None, pk=None):
        """Toggle schedule active state."""
        flow = self._get_flow(request, flow_pk)
        schedule = get_object_or_404(FlowSchedule, pk=pk, flow=flow)
        
        new_state = ScheduleService.toggle_schedule(schedule)
        schedule.refresh_from_db()
        
        return Response({
            'success': True,
            'message': f"Schedule {'activated' if new_state else 'deactivated'} successfully",
            'is_active': new_state,
            'schedule': self._serialize_schedule(schedule),
        })
