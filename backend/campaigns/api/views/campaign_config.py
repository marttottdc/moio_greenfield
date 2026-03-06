"""Campaign configuration endpoints (templates, defaults, schedule, audience)."""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from campaigns.api.serializers import (
    CampaignAudienceSerializer,
    CampaignDefaultsSerializer,
    CampaignDetailSerializer,
    CampaignMappingSerializer,
    CampaignWhatsappTemplateSerializer,
    ScheduleConfigSerializer,
)
from campaigns.core.service import (
    apply_mapping,
    fetch_whatsapp_template_requirements,
    update_defaults,
    update_schedule,
    update_template,
)
from campaigns.models import Audience, Campaign
from portal.context_utils import current_tenant
from portal.utils.tenants import TenantScopedViewSet


class CampaignConfigViewSet(TenantScopedViewSet):
    """Manage campaign configuration blocks."""

    permission_classes = [IsAuthenticated]
    lookup_field = "pk"
    serializer_class = CampaignDetailSerializer

    def get_queryset(self):
        tenant = current_tenant.get()
        return Campaign.objects.filter(tenant=tenant).select_related("audience")

    @extend_schema(
        request=CampaignWhatsappTemplateSerializer,
        responses={200: CampaignDetailSerializer},
        description="Update the WhatsApp template linked to the campaign message block.",
    )
    @action(detail=False, methods=["patch"], url_path="message")
    def update_template(self, request, pk=None):
        serializer = CampaignWhatsappTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.get_object()
        tenant = current_tenant.get()

        template_id = serializer.validated_data["template_id"]
        requirements = fetch_whatsapp_template_requirements(tenant, template_id)
        if requirements is None:
            raise serializers.ValidationError({"template_id": "WhatsApp integration disabled"})

        payload = update_template(campaign, template_id, requirements)
        return Response(payload)

    @extend_schema(
        request=CampaignDefaultsSerializer,
        responses={200: CampaignDetailSerializer},
        description="Update campaign default settings",
    )
    @action(detail=False, methods=["patch"], url_path="defaults")
    def update_defaults(self, request, pk=None):
        serializer = CampaignDefaultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.get_object()
        defaults = update_defaults(campaign, serializer.validated_data)
        return Response({"defaults": defaults})

    @extend_schema(
        request=ScheduleConfigSerializer,
        responses={200: CampaignDetailSerializer},
        description="Update or clear campaign schedule",
    )
    @action(detail=False, methods=["patch"], url_path="schedule")
    def update_schedule(self, request, pk=None):
        serializer = ScheduleConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.get_object()
        schedule_cfg = update_schedule(campaign, serializer.validated_data.get("date"))
        return Response({"schedule": schedule_cfg, "status": campaign.status})

    @extend_schema(
        request=CampaignMappingSerializer,
        responses={200: CampaignDetailSerializer},
        description="Apply variable mapping to the campaign template",
    )
    @action(detail=False, methods=["patch"], url_path="mapping")
    def apply_mapping(self, request, pk=None):
        serializer = CampaignMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.get_object()
        mapping = apply_mapping(
            campaign,
            list(serializer.validated_data["mapping"]),
            contact_field=serializer.validated_data.get("contact_name_field"),
        )
        return Response({"map": mapping})

    @extend_schema(
        request=CampaignAudienceSerializer,
        responses={200: CampaignDetailSerializer},
        description="Assign an audience to the campaign",
    )
    @action(detail=False, methods=["patch"], url_path="audience")
    def set_audience(self, request, pk=None):
        serializer = CampaignAudienceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = self.get_object()
        tenant = current_tenant.get()

        audience = Audience.objects.filter(
            pk=serializer.validated_data["audience_id"], tenant=tenant
        ).first()
        if not audience:
            raise serializers.ValidationError({"audience_id": "Audience not found"})

        campaign.audience = audience
        campaign.save(update_fields=["audience"])
        return Response(CampaignDetailSerializer(campaign).data)
