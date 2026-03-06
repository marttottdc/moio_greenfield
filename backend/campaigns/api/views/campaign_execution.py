"""Campaign execution endpoints (duplicate, launch, logs, job status)."""

from __future__ import annotations

from celery.result import AsyncResult
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from campaigns.api.serializers import CampaignDetailSerializer
from campaigns.core.service import (
    clone_campaign,
    log_campaign_activity,
    queue_campaign_validation,
)
from campaigns.models import Campaign
from moio_platform.celery_app import app
from portal.context_utils import current_tenant
from portal.utils.tenants import TenantScopedViewSet
from campaigns.tasks import execute_campaign
from moio_platform.api_schemas import Tags, STANDARD_ERRORS


class CampaignExecutionViewSet(TenantScopedViewSet):
    """Handle campaign lifecycle operations (launch, validate, duplicate)."""

    permission_classes = [IsAuthenticated]
    serializer_class = CampaignDetailSerializer
    lookup_field = "pk"

    def get_queryset(self):
        tenant = current_tenant.get()
        return Campaign.objects.filter(tenant=tenant).select_related("audience")

    @extend_schema(
        summary="Duplicate campaign",
        description="Create a copy of an existing campaign with a new name.",
        tags=[Tags.CAMPAIGNS],
        responses={201: CampaignDetailSerializer, **STANDARD_ERRORS},
    )
    @action(detail=False, methods=["post"], url_path="duplicate")
    def duplicate(self, request, pk=None):
        campaign = self.get_object()
        clone = clone_campaign(campaign)
        return Response(CampaignDetailSerializer(clone).data, status=201)

    @extend_schema(
        summary="Launch campaign",
        description="Start campaign execution. Queues a Celery task to send messages to the audience.",
        tags=[Tags.CAMPAIGNS],
        responses={
            200: OpenApiResponse(description="Job IDs for tracking execution"),
            **STANDARD_ERRORS,
        },
    )
    @action(detail=False, methods=["post"], url_path="launch")
    def launch(self, request, pk=None):
        campaign = self.get_object()
        job = execute_campaign.apply_async(
            args=[str(campaign.pk)],
            kwargs={"tenant_id": str(campaign.tenant_id)},
        )
        return Response({"jobs": [job.id]})

    @extend_schema(
        summary="Validate campaign",
        description="Queue campaign validation to check configuration, audience, and template requirements.",
        tags=[Tags.CAMPAIGNS],
        responses={
            200: OpenApiResponse(description="Validation job ID"),
            **STANDARD_ERRORS,
        },
    )
    @action(detail=False, methods=["post"], url_path="validate")
    def validate_campaign(self, request, pk=None):
        campaign = self.get_object()
        job_id = queue_campaign_validation(campaign)
        return Response({"job_id": job_id})

    @extend_schema(
        summary="Get campaign logs",
        description="Retrieve message delivery logs for a campaign.",
        tags=[Tags.CAMPAIGNS],
        responses={200: OpenApiResponse(description="Campaign activity logs")},
    )
    @action(detail=False, methods=["get"], url_path="logs")
    def logs(self, request, pk=None):
        campaign = self.get_object()
        tenant = current_tenant.get()
        logs = log_campaign_activity(campaign, tenant)
        return Response({"logs": logs})

    @extend_schema(
        summary="Get job status",
        description="Check the status of a campaign execution job.",
        tags=[Tags.CAMPAIGNS],
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Celery job ID"),
        ],
        responses={
            200: OpenApiResponse(description="Job status details"),
            403: OpenApiResponse(description="Forbidden - job belongs to different tenant"),
        },
    )
    @action(detail=False, methods=["get"], url_path=r"jobs/(?P<job_id>[^/.]+)")
    def job_status(self, request, pk=None, job_id: str = ""):
        result = AsyncResult(job_id, app=app)
        tenant = current_tenant.get()
        result_kwargs = result.kwargs or {}
        if result and result_kwargs.get("tenant_id") != str(getattr(tenant, "id", None)):
            return Response({"detail": "Forbidden"}, status=403)
        return Response(
            {
                "campaign_pk": str(pk),
                "job_id": job_id,
                "status": result.status,
                "ready": result.ready(),
                "successful": result.successful() if result.ready() else None,
                "result": result.result if result.ready() else None,
            }
        )
