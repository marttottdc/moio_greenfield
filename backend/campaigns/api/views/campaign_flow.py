"""
Campaign Flow V2 API - FSM-based campaign transition endpoints.

Provides RESTful endpoints for campaign state transitions with proper validation,
plus SSE streaming for live campaign monitoring.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from django.db import transaction
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from campaigns.api.serializers import CampaignDetailSerializer
from campaigns.core.campaign_flow_v2 import (
    CampaignFlowV2,
    CampaignStep,
    EndReason,
    get_campaign_flow,
    get_campaign_requirements,
    ConfigurationState,
)
from campaigns.core.service import fetch_whatsapp_template_requirements
from campaigns.models import Audience, Campaign, CampaignData, CampaignDataStatus
from campaigns.tasks import execute_campaign
from moio_platform.core.events import emit_event
from central_hub.context_utils import current_tenant
from central_hub.utils.tenants import TenantScopedViewSet

logger = logging.getLogger(__name__)


class TransitionPayloadSerializer(serializers.Serializer):
    """Base serializer for transition payloads."""
    pass


class SelectTemplateSerializer(TransitionPayloadSerializer):
    """Payload for template selection."""
    template_id = serializers.CharField(required=True)


class ImportDataSerializer(TransitionPayloadSerializer):
    """Payload for data import."""
    staging_id = serializers.UUIDField(required=True)
    headers = serializers.ListField(child=serializers.CharField(), required=True)
    row_count = serializers.IntegerField(required=True, min_value=1)


class ConfigureMappingSerializer(TransitionPayloadSerializer):
    """Payload for mapping configuration."""
    mapping = serializers.ListField(child=serializers.DictField(), required=True)
    contact_name_field = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class SetAudienceSerializer(TransitionPayloadSerializer):
    """Payload for audience selection."""
    audience_id = serializers.UUIDField(required=True)


class SetScheduleSerializer(TransitionPayloadSerializer):
    """Payload for schedule configuration."""
    schedule_date = serializers.DateTimeField(required=True)


class CompleteSerializer(TransitionPayloadSerializer):
    """Payload for campaign completion."""
    reason = serializers.ChoiceField(
        choices=[(r.value, r.name) for r in EndReason],
        required=False,
        default=EndReason.SUCCESS.value
    )


class CampaignFlowSerializer(serializers.ModelSerializer):
    """Extended serializer with flow state information."""
    
    configuration_state = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    current_step = serializers.SerializerMethodField()
    missing_requirements = serializers.SerializerMethodField()
    requirements = serializers.SerializerMethodField()
    
    class Meta:
        model = Campaign
        fields = [
            "id", "name", "description", "channel", "kind", "status",
            "sent", "opened", "responded", "created", "updated",
            "configuration_state", "allowed_actions", "current_step",
            "missing_requirements", "requirements", "config",
        ]
        read_only_fields = fields
    
    def get_configuration_state(self, obj) -> Dict[str, Any]:
        flow = get_campaign_flow(obj)
        return flow.get_configuration_state().to_dict()
    
    def get_allowed_actions(self, obj) -> list:
        flow = get_campaign_flow(obj)
        return flow.get_allowed_actions()
    
    def get_current_step(self, obj) -> str:
        config = obj.config or {}
        return config.get("current_step", "draft")
    
    def get_missing_requirements(self, obj) -> list:
        flow = get_campaign_flow(obj)
        return flow.get_missing_requirements()
    
    def get_requirements(self, obj) -> Dict[str, Any]:
        reqs = get_campaign_requirements(obj.channel, obj.kind)
        return {
            "steps": reqs.steps,
            "optional_steps": reqs.optional_steps,
            "required_for_ready": reqs.required_for_ready,
            "schedule_required": reqs.schedule_required,
        }


@extend_schema(tags=["Campaign Flow V2"])
class CampaignFlowViewSet(TenantScopedViewSet):
    """
    FSM-based campaign flow management.
    
    Provides transition endpoints that enforce proper sequencing
    and validation for campaign creation and lifecycle.
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = CampaignFlowSerializer
    lookup_field = "pk"
    
    def get_queryset(self):
        tenant = current_tenant.get()
        return Campaign.objects.filter(tenant=tenant).select_related("audience")
    
    def _transition_response(self, campaign: Campaign, message: str = "Transition successful"):
        """Build standardized transition response."""
        return Response({
            "success": True,
            "message": message,
            "campaign": CampaignFlowSerializer(campaign).data,
        })
    
    def _error_response(self, error: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        """Build standardized error response."""
        return Response({
            "success": False,
            "error": error,
        }, status=status_code)
    
    @extend_schema(
        request=SelectTemplateSerializer,
        responses={200: CampaignFlowSerializer},
        description="Select a message template for the campaign"
    )
    @action(detail=True, methods=["post"], url_path="transitions/select-template")
    def select_template(self, request, pk=None):
        """Select template transition."""
        serializer = SelectTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        campaign = self.get_object()
        tenant = current_tenant.get()
        template_id = serializer.validated_data["template_id"]
        
        requirements = None
        if campaign.channel == "whatsapp":
            requirements = fetch_whatsapp_template_requirements(tenant, template_id)
            if requirements is None:
                return self._error_response("WhatsApp integration not configured or template not found")
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.select_template(template_id, requirements)
        except ValueError as e:
            return self._error_response(str(e))
        
        return self._transition_response(campaign, f"Template {template_id} selected")
    
    @extend_schema(
        request=ImportDataSerializer,
        responses={200: CampaignFlowSerializer},
        description="Import data from staging for the campaign"
    )
    @action(detail=True, methods=["post"], url_path="transitions/import-data")
    def import_data(self, request, pk=None):
        """Import data transition."""
        serializer = ImportDataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.import_data(
                    staging_id=str(serializer.validated_data["staging_id"]),
                    headers=serializer.validated_data["headers"],
                    row_count=serializer.validated_data["row_count"],
                )
        except ValueError as e:
            return self._error_response(str(e))
        
        return self._transition_response(campaign, "Data imported successfully")
    
    @extend_schema(
        request=ConfigureMappingSerializer,
        responses={200: CampaignFlowSerializer},
        description="Configure variable mapping between data and template"
    )
    @action(detail=True, methods=["post"], url_path="transitions/configure-mapping")
    def configure_mapping(self, request, pk=None):
        """Configure mapping transition."""
        serializer = ConfigureMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.configure_mapping(
                    mapping=serializer.validated_data["mapping"],
                    contact_name_field=serializer.validated_data.get("contact_name_field"),
                )
        except ValueError as e:
            return self._error_response(str(e))
        
        return self._transition_response(campaign, "Mapping configured")
    
    @extend_schema(
        request=SetAudienceSerializer,
        responses={200: CampaignFlowSerializer},
        description="Set target audience for the campaign"
    )
    @action(detail=True, methods=["post"], url_path="transitions/set-audience")
    def set_audience(self, request, pk=None):
        """Set audience transition."""
        serializer = SetAudienceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        campaign = self.get_object()
        tenant = current_tenant.get()
        
        audience = Audience.objects.filter(
            pk=serializer.validated_data["audience_id"],
            tenant=tenant
        ).first()
        
        if not audience:
            return self._error_response("Audience not found", status.HTTP_404_NOT_FOUND)
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.set_audience(audience)
        except ValueError as e:
            return self._error_response(str(e))
        
        return self._transition_response(campaign, f"Audience '{audience.name}' set")
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Mark campaign as ready for launch"
    )
    @action(detail=True, methods=["post"], url_path="transitions/mark-ready")
    def mark_ready(self, request, pk=None):
        """Mark ready transition."""
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.mark_ready()
        except ValueError as e:
            return self._error_response(str(e))
        
        return self._transition_response(campaign, "Campaign is ready for launch")
    
    @extend_schema(
        request=SetScheduleSerializer,
        responses={200: CampaignFlowSerializer},
        description="Set a schedule date for the campaign"
    )
    @action(detail=True, methods=["post"], url_path="transitions/set-schedule")
    def set_schedule(self, request, pk=None):
        """Set schedule transition."""
        serializer = SetScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        campaign = self.get_object()
        schedule_date = serializer.validated_data["schedule_date"]
        
        if schedule_date <= timezone.now():
            return self._error_response("Schedule date must be in the future")
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.set_schedule(schedule_date.isoformat())
        except ValueError as e:
            return self._error_response(str(e))
        
        return self._transition_response(campaign, f"Scheduled for {schedule_date}")
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Confirm schedule and move to SCHEDULED state"
    )
    @action(detail=True, methods=["post"], url_path="transitions/schedule-launch")
    def schedule_launch(self, request, pk=None):
        """Schedule launch transition."""
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.schedule_launch()
        except ValueError as e:
            return self._error_response(str(e))
        
        config = campaign.config or {}
        schedule = config.get("schedule", {})
        CampaignEventPublisher.publish(
            str(campaign.pk),
            "campaign_scheduled",
            {"schedule_date": schedule.get("date"), "status": "scheduled"}
        )
        
        return self._transition_response(campaign, "Launch scheduled")
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Launch the campaign immediately"
    )
    @action(detail=True, methods=["post"], url_path="transitions/launch-now")
    def launch_now(self, request, pk=None):
        """Launch campaign immediately."""
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.launch_now()
        except ValueError as e:
            return self._error_response(str(e))
        
        job = execute_campaign.apply_async(
            args=[str(campaign.pk)],
            kwargs={"tenant_id": str(campaign.tenant_id)},
        )
        
        CampaignEventPublisher.publish(
            str(campaign.pk),
            "campaign_launched",
            {"job_id": job.id, "status": "active"}
        )
        
        return Response({
            "success": True,
            "message": "Campaign launched",
            "job_id": job.id,
            "campaign": CampaignFlowSerializer(campaign).data,
        })
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Cancel scheduled launch"
    )
    @action(detail=True, methods=["post"], url_path="transitions/cancel-schedule")
    def cancel_schedule(self, request, pk=None):
        """Cancel scheduled launch."""
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.cancel_schedule()
        except ValueError as e:
            return self._error_response(str(e))
        
        CampaignEventPublisher.publish(
            str(campaign.pk),
            "schedule_cancelled",
            {"status": "ready"}
        )
        
        return self._transition_response(campaign, "Schedule cancelled")
    
    @extend_schema(
        request=CompleteSerializer,
        responses={200: CampaignFlowSerializer},
        description="Mark campaign as completed"
    )
    @action(detail=True, methods=["post"], url_path="transitions/complete")
    def complete(self, request, pk=None):
        """Complete campaign transition."""
        serializer = CompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        campaign = self.get_object()
        reason = EndReason(serializer.validated_data.get("reason", EndReason.SUCCESS.value))
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.complete(reason)
        except ValueError as e:
            return self._error_response(str(e))
        
        CampaignEventPublisher.campaign_completed(
            str(campaign.pk),
            reason.value,
            {"sent": campaign.sent, "opened": campaign.opened, "responded": campaign.responded}
        )

        try:
            emit_event(
                name="campaign.completed",
                tenant_id=campaign.tenant.tenant_code,
                actor={"type": "user", "id": str(request.user.id)},
                entity={"type": "campaign", "id": str(campaign.pk)},
                payload={
                    "campaign_id": str(campaign.pk),
                    "name": campaign.name,
                    "reason": reason.value,
                    "sent": campaign.sent,
                    "opened": campaign.opened,
                    "responded": campaign.responded,
                    "completed_at": timezone.now().isoformat(),
                },
                source="api",
            )
        except Exception:
            pass
        
        return self._transition_response(campaign, f"Campaign completed: {reason.value}")
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Cancel an active campaign"
    )
    @action(detail=True, methods=["post"], url_path="transitions/cancel")
    def cancel(self, request, pk=None):
        """Cancel campaign transition."""
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.cancel()
        except ValueError as e:
            return self._error_response(str(e))
        
        CampaignEventPublisher.campaign_completed(
            str(campaign.pk),
            "cancelled",
            {"sent": campaign.sent, "opened": campaign.opened, "responded": campaign.responded}
        )
        
        return self._transition_response(campaign, "Campaign cancelled")
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Rollback to configuration state"
    )
    @action(detail=True, methods=["post"], url_path="transitions/rollback")
    def rollback(self, request, pk=None):
        """Rollback transition."""
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.rollback()
        except ValueError as e:
            return self._error_response(str(e))
        
        campaign.refresh_from_db()
        config = campaign.config or {}
        current_step = config.get("current_step", CampaignStep.SET_AUDIENCE.value)
        
        CampaignEventPublisher.publish(
            str(campaign.pk),
            "campaign_rollback",
            {"status": campaign.status, "step": current_step}
        )
        
        return self._transition_response(campaign, "Rolled back to configuration")
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Archive a completed campaign"
    )
    @action(detail=True, methods=["post"], url_path="transitions/archive")
    def archive(self, request, pk=None):
        """Archive campaign transition."""
        campaign = self.get_object()
        
        try:
            with transaction.atomic():
                flow = get_campaign_flow(campaign)
                flow.archive()
        except ValueError as e:
            return self._error_response(str(e))
        
        CampaignEventPublisher.publish(
            str(campaign.pk),
            "campaign_archived",
            {"status": "archived"}
        )
        
        return self._transition_response(campaign, "Campaign archived")
    
    @extend_schema(
        responses={200: CampaignFlowSerializer},
        description="Get current flow state and available actions"
    )
    @action(detail=True, methods=["get"], url_path="flow-state")
    def flow_state(self, request, pk=None):
        """Get current flow state without making any transition."""
        campaign = self.get_object()
        return Response(CampaignFlowSerializer(campaign).data)


class CampaignStreamView(APIView):
    """
    SSE endpoint for live campaign monitoring.
    
    Streams real-time campaign statistics and message status updates.
    Filter by campaign_id query parameter for specific campaign monitoring.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Stream campaign events via SSE."""
        campaign_id = request.query_params.get("campaign_id")
        tenant = current_tenant.get()
        
        def event_stream():
            last_stats = {}
            heartbeat_counter = 0
            
            while True:
                try:
                    heartbeat_counter += 1
                    
                    if heartbeat_counter % 15 == 0:
                        yield f": heartbeat {timezone.now().isoformat()}\n\n"
                    
                    campaigns_qs = Campaign.objects.filter(tenant=tenant, status="active")
                    if campaign_id:
                        campaigns_qs = campaigns_qs.filter(pk=campaign_id)
                    
                    for campaign in campaigns_qs:
                        stats = self._get_campaign_stats(campaign)
                        campaign_key = str(campaign.pk)
                        
                        if campaign_key not in last_stats or last_stats[campaign_key] != stats:
                            last_stats[campaign_key] = stats
                            event_data = {
                                "event": "stats",
                                "campaign_id": campaign_key,
                                "campaign_name": campaign.name,
                                "status": campaign.status,
                                **stats,
                                "timestamp": timezone.now().isoformat(),
                            }
                            yield f"data: {json.dumps(event_data)}\n\n"
                    
                    import time
                    time.sleep(2)
                    
                except GeneratorExit:
                    break
                except Exception as e:
                    logger.error(f"SSE stream error: {e}")
                    error_data = {"event": "error", "message": str(e)}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break
        
        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
    
    def _get_campaign_stats(self, campaign: Campaign) -> Dict[str, Any]:
        """Get current statistics for a campaign."""
        data_qs = CampaignData.objects.filter(campaign=campaign)
        
        total = data_qs.count()
        pending = data_qs.filter(status=CampaignDataStatus.PENDING).count()
        sent = data_qs.filter(status=CampaignDataStatus.SENT).count()
        delivered = data_qs.filter(status=CampaignDataStatus.DELIVERED).count()
        failed = data_qs.filter(status=CampaignDataStatus.FAILED).count()
        skipped = data_qs.filter(status=CampaignDataStatus.SKIPPED).count()
        
        return {
            "total": total,
            "pending": pending,
            "sent": sent,
            "delivered": delivered,
            "failed": failed,
            "skipped": skipped,
            "progress_percent": round((sent + delivered + failed + skipped) / total * 100, 1) if total > 0 else 0,
            "success_rate": round(delivered / (delivered + failed) * 100, 1) if (delivered + failed) > 0 else 0,
        }


class CampaignEventPublisher:
    """
    Publisher for campaign events to SSE stream.
    
    Can be called from Celery tasks or signal handlers to broadcast
    real-time updates to connected clients.
    """
    
    _listeners: Dict[str, list] = {}
    
    @classmethod
    def publish(cls, campaign_id: str, event_type: str, data: Dict[str, Any]):
        """Publish an event for a campaign."""
        event = {
            "event": event_type,
            "campaign_id": campaign_id,
            "data": data,
            "timestamp": timezone.now().isoformat(),
        }
        logger.info(f"Campaign event published: {event_type} for {campaign_id}")
        return event
    
    @classmethod
    def message_sent(cls, campaign_id: str, contact_id: str, message_id: str):
        """Publish message sent event."""
        return cls.publish(campaign_id, "message_sent", {
            "contact_id": contact_id,
            "message_id": message_id,
        })
    
    @classmethod
    def message_delivered(cls, campaign_id: str, contact_id: str, message_id: str):
        """Publish message delivered event."""
        return cls.publish(campaign_id, "message_delivered", {
            "contact_id": contact_id,
            "message_id": message_id,
        })
    
    @classmethod
    def message_failed(cls, campaign_id: str, contact_id: str, error: str):
        """Publish message failed event."""
        return cls.publish(campaign_id, "message_failed", {
            "contact_id": contact_id,
            "error": error,
        })
    
    @classmethod
    def campaign_completed(cls, campaign_id: str, reason: str, stats: Dict[str, Any]):
        """Publish campaign completed event."""
        return cls.publish(campaign_id, "campaign_completed", {
            "reason": reason,
            "stats": stats,
        })
