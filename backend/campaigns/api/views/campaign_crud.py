"""CRUD + analytics endpoints for campaigns and audiences."""

from __future__ import annotations

from datetime import datetime, time

from django.db import transaction
from django.db.models import Avg, Case, Count, DateTimeField, Max, When, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from campaigns.api.serializers import (
    AudienceDetailSerializer,
    AudienceRulesSerializer,
    AudienceSerializer,
    AudienceStaticContactsSerializer,
    CampaignDetailSerializer,
    CampaignSerializer,
)
from campaigns.core.audience_filters import compute_audience, compute_audience_preview
from campaigns.core.campaigns_engine import set_base_config
from campaigns.core.service import add_static_contacts, remove_static_contacts
from campaigns.models import Audience, AudienceKind, Campaign, Status
from chatbot.models.wa_message_log import WaMessageLog
from crm.models import Contact
from central_hub.context_utils import current_tenant
from central_hub.utils.tenants import TenantScopedViewSet
from central_hub.models import Tenant
from moio_platform.api_schemas import Tags, STANDARD_ERRORS


@extend_schema_view(
    list=extend_schema(
        summary="List campaigns",
        description="Retrieve a paginated list of campaigns for the current tenant.",
        tags=[Tags.CAMPAIGNS],
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR, description="Search by campaign name"),
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by status: draft, scheduled, active, completed"),
            OpenApiParameter("channel", OpenApiTypes.STR, description="Filter by channel: whatsapp, email"),
        ],
    ),
    retrieve=extend_schema(
        summary="Get campaign details",
        description="Retrieve detailed campaign information including configuration and audience.",
        tags=[Tags.CAMPAIGNS],
    ),
    create=extend_schema(
        summary="Create campaign",
        description="Create a new marketing campaign. Initial configuration is auto-generated.",
        tags=[Tags.CAMPAIGNS],
    ),
    update=extend_schema(
        summary="Update campaign",
        description="Update campaign details.",
        tags=[Tags.CAMPAIGNS],
    ),
    partial_update=extend_schema(
        summary="Partial update campaign",
        description="Partially update campaign fields.",
        tags=[Tags.CAMPAIGNS],
    ),
    destroy=extend_schema(
        summary="Delete campaign",
        description="Delete a campaign. Cannot delete active campaigns.",
        tags=[Tags.CAMPAIGNS],
        responses={409: OpenApiResponse(description="Campaign is active and cannot be deleted")},
    ),
)
class CampaignCrudViewSet(TenantScopedViewSet):
    """CRUD + read-only analytics endpoints for campaigns."""

    permission_classes = [IsAuthenticated]
    serializer_class = CampaignSerializer
    lookup_field = "pk"

    def get_queryset(self):
        # Ensure tenant is resolved from request.user if context not set
        tenant = current_tenant.get() or getattr(self.request.user, 'tenant', None)
        if not tenant:
            return Campaign.objects.none()
        
        # Ensure tenant context is set for consistency
        if current_tenant.get() != tenant:
            current_tenant.set(tenant)
        
        return Campaign.objects.filter(tenant=tenant).select_related("audience")

    def get_serializer_class(self):
        if self.action in {"retrieve", "update", "partial_update"}:
            return CampaignDetailSerializer
        return super().get_serializer_class()

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        request = self.request
        search = request.query_params.get("search", "").strip()
        status_filter = request.query_params.get("status")
        channel_filter = request.query_params.get("channel")

        if search:
            qs = qs.filter(name__icontains=search)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if channel_filter:
            qs = qs.filter(channel=channel_filter)
        return qs.order_by("-created")

    def perform_create(self, serializer):
        # Ensure tenant is resolved from request.user if context not set
        tenant = current_tenant.get() or getattr(self.request.user, 'tenant', None)
        if not tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("User must belong to a tenant")
        
        # Ensure tenant context is set
        if current_tenant.get() != tenant:
            current_tenant.set(tenant)
        
        campaign = serializer.save(tenant=tenant)
        campaign.config = set_base_config(campaign)
        campaign.save(update_fields=["config"])

    def destroy(self, request, *args, **kwargs):
        campaign = self.get_object()
        if campaign.status == Status.ACTIVE:
            return Response(
                {
                    "error": "cannot_delete_active",
                    "message": "Cannot delete a campaign while it is active. End or archive the campaign first.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Campaign dashboard",
        description="Get dashboard with campaigns, audiences, and aggregated metrics.",
        tags=[Tags.CAMPAIGNS],
        responses={200: OpenApiResponse(description="Dashboard data with campaigns and metrics")},
    )
    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        # Ensure tenant is resolved from request.user if context not set
        tenant = current_tenant.get() or getattr(self.request.user, 'tenant', None)
        if not tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("User must belong to a tenant")
        
        # Ensure tenant context is set
        if current_tenant.get() != tenant:
            current_tenant.set(tenant)
        
        campaigns = self.get_queryset()
        audiences = Audience.objects.filter(tenant=tenant)
        total_sent = sum(c.sent for c in campaigns)
        total_opened = sum(c.opened for c in campaigns)

        serializer = CampaignSerializer(campaigns, many=True)
        data = {
            "campaigns": serializer.data,
            "audiences": AudienceSerializer(audiences, many=True).data,
            "channels": [choice[0] for choice in Campaign._meta.get_field("channel").choices],
            "statuses": [choice[0] for choice in Campaign._meta.get_field("status").choices],
            "dashboard_metrics": {
                "total_campaigns": campaigns.count(),
                "active_campaigns": campaigns.filter(status=Status.ACTIVE).count(),
                "total_sent": total_sent,
                "total_opened": total_opened,
                "open_rate": (total_opened / total_sent * 100) if total_sent else 0,
            },
        }
        return Response(data)

    @extend_schema(
        summary="Campaign analytics",
        description="Get detailed analytics including message volume, delivery performance, and user engagement.",
        tags=[Tags.CAMPAIGNS],
        parameters=[
            OpenApiParameter("tenant", OpenApiTypes.STR, description="Tenant ID (staff only)"),
            OpenApiParameter("start_date", OpenApiTypes.DATE, description="Start date filter (YYYY-MM-DD)"),
            OpenApiParameter("end_date", OpenApiTypes.DATE, description="End date filter (YYYY-MM-DD)"),
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by message status"),
            OpenApiParameter("origin", OpenApiTypes.STR, description="Filter by message origin"),
            OpenApiParameter("q", OpenApiTypes.STR, description="Search query"),
        ],
        responses={200: OpenApiResponse(description="Analytics data")},
    )
    @action(detail=False, methods=["get"], url_path="analytics")
    def analytics(self, request):
        tenant = current_tenant.get()
        tenant_id = request.query_params.get("tenant")
        start_param = request.query_params.get("start_date")
        end_param = request.query_params.get("end_date")
        status_param = request.query_params.get("status")
        origin_param = request.query_params.get("origin")
        search_query = request.query_params.get("q")

        queryset = WaMessageLog.objects.filter(tenant=tenant)
        selected_tenant = tenant

        if request.user.is_staff and tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
            selected_tenant = Tenant.objects.filter(id=tenant_id).first()

        if start_param:
            start_date = parse_date(start_param)
            if start_date:
                start_dt = datetime.combine(start_date, time.min)
                if timezone.is_naive(start_dt):
                    start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
                queryset = queryset.filter(created__gte=start_dt)

        if end_param:
            end_date = parse_date(end_param)
            if end_date:
                end_dt = datetime.combine(end_date, time.max)
                if timezone.is_naive(end_dt):
                    end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
                queryset = queryset.filter(created__lte=end_dt)

        if status_param:
            queryset = queryset.filter(status=status_param)
        if origin_param:
            queryset = queryset.filter(origin=origin_param)

        volume_data = (
            queryset.annotate(day=TruncDate("created"))
            .values("day")
            .annotate(total=Count("id"))
            .order_by("day")
        )
        volume_per_day = [
            {
                "day": entry["day"].isoformat() if entry["day"] else None,
                "label": entry["day"].strftime("%Y-%m-%d") if entry["day"] else "",
                "total": entry["total"],
            }
            for entry in volume_data
        ]

        delivery_performance = list(
            queryset.values("status").annotate(total=Count("id")).order_by("-total")
        )

        top_users = list(
            queryset.values("user_name", "user_number")
            .annotate(total=Count("id"))
            .order_by("-total")[:10]
        )

        conversation_counts = (
            queryset.exclude(conversation_id__isnull=True)
            .values("conversation_id")
            .annotate(total=Count("id"))
        )
        average_messages = conversation_counts.aggregate(avg=Avg("total"))["avg"] or 0
        total_conversations = conversation_counts.count()

        data = {
            "volume_per_day": volume_per_day,
            "delivery_performance": delivery_performance,
            "top_users": top_users,
            "conversation_summary": {
                "average_messages": average_messages,
                "total_conversations": total_conversations,
                "total_messages": queryset.count(),
                "unique_users": queryset.values("user_number").distinct().count(),
            },
            "filters": {
                "tenant": str(tenant_id) if tenant_id else (str(selected_tenant.id) if selected_tenant else None),
                "start_date": start_param,
                "end_date": end_param,
                "status": status_param,
                "origin": origin_param,
                "q": search_query or "",
            },
        }
        return Response(data)


@extend_schema_view(
    list=extend_schema(
        summary="List audiences",
        description="Retrieve all audiences for the current tenant.",
        tags=[Tags.AUDIENCES],
    ),
    retrieve=extend_schema(
        summary="Get audience details",
        description="Retrieve detailed audience information including rules and size.",
        tags=[Tags.AUDIENCES],
    ),
    create=extend_schema(
        summary="Create audience",
        description="Create a new audience. Starts as draft until finalized.",
        tags=[Tags.AUDIENCES],
    ),
    update=extend_schema(
        summary="Update audience",
        description="Update audience details.",
        tags=[Tags.AUDIENCES],
    ),
    partial_update=extend_schema(
        summary="Partial update audience",
        description="Partially update audience fields.",
        tags=[Tags.AUDIENCES],
    ),
    destroy=extend_schema(
        summary="Delete audience",
        description="Delete an audience.",
        tags=[Tags.AUDIENCES],
    ),
)
class AudienceViewSet(TenantScopedViewSet):
    """Audience CRUD + rule management endpoints."""

    permission_classes = [IsAuthenticated]
    serializer_class = AudienceSerializer
    lookup_field = "pk"

    def get_queryset(self):
        tenant = current_tenant.get() or getattr(self.request.user, "tenant", None)
        if not tenant:
            return Audience.objects.none()
        if current_tenant.get() != tenant:
            current_tenant.set(tenant)
        return Audience.objects.filter(tenant=tenant)

    def get_serializer_class(self):
        if self.action in {"retrieve", "update", "partial_update"}:
            return AudienceDetailSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        serializer.save(tenant=current_tenant.get(), is_draft=True)

    @extend_schema(
        summary="Preview dynamic audience",
        description="Preview the count of contacts that would match the given rules without saving.",
        tags=[Tags.AUDIENCES],
        request=AudienceRulesSerializer,
        responses={200: OpenApiResponse(description="Preview count")},
    )
    @action(detail=True, methods=["post"], url_path="dynamic/preview")
    def preview_dynamic(self, request, pk=None):
        serializer = AudienceRulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = current_tenant.get()
        base_qs = Contact.objects.filter(tenant=tenant)
        count = compute_audience_preview(
            serializer.validated_data["and_rules"],
            serializer.validated_data["or_rules"],
            base_qs,
        )
        return Response({"count": count})

    @extend_schema(
        summary="Autosave dynamic audience",
        description="Save rules and compute membership without finalizing. Keeps audience in draft state.",
        tags=[Tags.AUDIENCES],
        request=AudienceRulesSerializer,
        responses={200: OpenApiResponse(description="Count of matched contacts")},
    )
    @action(detail=True, methods=["post"], url_path="dynamic/autosave")
    def autosave_dynamic(self, request, pk=None):
        serializer = AudienceRulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        audience = self.get_object()
        tenant = current_tenant.get()
        base_qs = Contact.objects.filter(tenant=tenant)

        with transaction.atomic():
            audience.rules = {
                "and": serializer.validated_data["and_rules"],
                "or": serializer.validated_data["or_rules"],
            }
            audience.is_draft = True
            audience.save(update_fields=["rules", "is_draft"])
            matched = compute_audience(
                serializer.validated_data["and_rules"],
                serializer.validated_data["or_rules"],
                base_qs,
                audience=audience,
                m2m_attr="contacts",
                replace=True,
                m2m_through_defaults={"tenant": tenant},
            )
        return Response({"count": matched.count()})

    @extend_schema(
        summary="Finalize dynamic audience",
        description="Save rules, compute membership, and mark audience as finalized (not draft).",
        tags=[Tags.AUDIENCES],
        request=AudienceRulesSerializer,
        responses={200: AudienceDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="dynamic/finalize")
    def finalize_dynamic(self, request, pk=None):
        serializer = AudienceRulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        audience = self.get_object()
        tenant = current_tenant.get()
        base_qs = Contact.objects.filter(tenant=tenant)

        with transaction.atomic():
            audience.rules = {
                "and": serializer.validated_data["and_rules"],
                "or": serializer.validated_data["or_rules"],
            }
            audience.is_draft = False
            audience.save(update_fields=["rules", "is_draft"])
            matched = compute_audience(
                serializer.validated_data["and_rules"],
                serializer.validated_data["or_rules"],
                base_qs,
                audience=audience,
                m2m_attr="contacts",
                replace=True,
                m2m_through_defaults={"tenant": tenant},
            )
            audience.size = matched.count()
            audience.save(update_fields=["size"])
        return Response(AudienceDetailSerializer(audience).data)

    @extend_schema(
        summary="Add/remove static contacts",
        description="Add or remove contacts from a static audience.",
        tags=[Tags.AUDIENCES],
        request=AudienceStaticContactsSerializer,
        responses={200: OpenApiResponse(description="Affected count and new size")},
    )
    @action(detail=True, methods=["post"], url_path="static/contacts")
    def static_contacts(self, request, pk=None):
        serializer = AudienceStaticContactsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        audience = self.get_object()
        if audience.kind != AudienceKind.STATIC:
            raise serializers.ValidationError(
                {"audience": "Manual updates allowed only for static audiences"}
            )

        contact_ids = serializer.validated_data["contact_ids"]
        contacts = Contact.objects.filter(pk__in=contact_ids, tenant=current_tenant.get())

        if serializer.validated_data["action"] == "add":
            created, _ = add_static_contacts(audience, contacts)
            affected = created
        else:
            deleted, _ = remove_static_contacts(audience, contacts)
            affected = deleted

        audience.refresh_from_db(fields=["size"])
        return Response({"affected": affected, "size": audience.size})

    @extend_schema(
        summary="Finalize static audience",
        description="Mark static audience as finalized (not draft) and update size.",
        tags=[Tags.AUDIENCES],
        responses={200: AudienceDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="static/finalize")
    def finalize_static(self, request, pk=None):
        audience = self.get_object()
        audience.size = audience.membership.count()
        audience.is_draft = False
        audience.save(update_fields=["size", "is_draft"])
        return Response(AudienceDetailSerializer(audience).data)

    @extend_schema(
        summary="List audience contacts",
        description="Get a preview of contacts in the audience (limited to 50).",
        tags=[Tags.AUDIENCES],
        responses={200: OpenApiResponse(description="Contact list with count")},
    )
    @action(detail=True, methods=["get"], url_path="contacts")
    def contacts(self, request, pk=None):
        audience = self.get_object()
        memberships = audience.membership.select_related("contact").order_by("-created")[:50]
        results = [
            {
                "id": str(m.contact_id),
                "fullname": m.contact.fullname,
                "phone": m.contact.phone,
                "email": m.contact.email,
            }
            for m in memberships
            if m.contact
        ]
        return Response({"results": results, "count": audience.size})

    @extend_schema(
        summary="Get WhatsApp logs",
        description="Get consolidated WhatsApp message logs for a campaign, grouped by message ID.",
        tags=[Tags.AUDIENCES],
        parameters=[
            OpenApiParameter("campaign_id", OpenApiTypes.UUID, required=True, description="Campaign ID to get logs for"),
        ],
        responses={
            200: OpenApiResponse(description="WhatsApp logs grouped by message"),
            400: OpenApiResponse(description="campaign_id is required"),
            404: OpenApiResponse(description="Campaign not found"),
        },
    )
    @action(detail=False, methods=["get"], url_path="whatsapp-logs")
    def whatsapp_logs(self, request):
        """
        Consolidated WhatsApp logs for a campaign, grouped by msg_id.
        
        Query params:
            - campaign_id (required)
        
        The model WaMessageLog does not store campaign_id explicitly; we try to
        match logs using conversation_id OR msg_content.campaign_id.
        """
        tenant = current_tenant.get() or getattr(request.user, "tenant", None)
        if not tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("User must belong to a tenant")
        
        campaign_id = request.query_params.get("campaign_id")
        if not campaign_id:
            return Response({"ok": False, "error": "campaign_id is required"}, status=400)
        
        try:
            campaign = Campaign.objects.get(id=campaign_id, tenant=tenant)
        except Campaign.DoesNotExist:
            return Response({"ok": False, "error": "Campaign not found"}, status=404)
        
        logs = (
            WaMessageLog.objects.filter(tenant=tenant)
            .filter(Q(conversation_id=campaign_id) | Q(msg_content__campaign_id=campaign_id))
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
                    "flow_execution_id": str(log.flow_execution_id) if getattr(log, "flow_execution_id", None) else None,
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

            if not bucket.get("flow_execution_id") and getattr(log, "flow_execution_id", None):
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
            contacts = (
                Contact.objects.filter(tenant=tenant)
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
                "campaign": {"id": str(campaign.id), "name": campaign.name},
                "message_count": len(messages),
                "messages": messages,
            }
        )
