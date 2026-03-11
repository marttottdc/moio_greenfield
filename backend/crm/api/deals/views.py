from django.db.models import Sum, Count, Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.response import Response

from crm.api.mixins import PaginationMixin, ProtectedAPIView
from moio_platform.core.events import emit_event
from moio_platform.core.events.snapshots import snapshot_contact, snapshot_deal
from crm.models import Deal, Pipeline, PipelineStage, DealStatusChoices, Customer
from crm.api.deals.serializers import (
    DealSerializer, DealCreateSerializer, DealUpdateSerializer,
    PipelineSerializer, PipelineCreateSerializer, PipelineStageSerializer,
    DealStageUpdateSerializer, DealCommentSerializer
)


@extend_schema(tags=["deals"])
class DealsView(PaginationMixin, ProtectedAPIView):
    DEFAULT_PAGE_SIZE = 50

    def get(self, request):
        tenant = self._get_tenant(request)
        deals = Deal.objects.filter(tenant=tenant).select_related(
            'contact', 'pipeline', 'stage', 'owner'
        )

        deal_status = request.query_params.get('status')
        if deal_status:
            deals = deals.filter(status=deal_status)

        pipeline_id = request.query_params.get('pipeline')
        if pipeline_id:
            deals = deals.filter(pipeline_id=pipeline_id)

        stage_id = request.query_params.get('stage')
        if stage_id:
            deals = deals.filter(stage_id=stage_id)

        priority = request.query_params.get('priority')
        if priority:
            deals = deals.filter(priority=priority)

        owner_id = request.query_params.get('owner')
        if owner_id:
            deals = deals.filter(owner_id=owner_id)

        customer_id = request.query_params.get('customer_id')
        if customer_id:
            customer = Customer.objects.filter(tenant=tenant, id=customer_id).first()
            if customer:
                deals = deals.filter(
                    Q(customer_id=customer_id)
                    | Q(contact__customer_contacts__customer_id=customer_id)
                    | Q(contact__company__iexact=customer.name)
                ).distinct()
            else:
                deals = deals.filter(customer_id=customer_id)

        contact_id = request.query_params.get('contact_id')
        if contact_id:
            deals = deals.filter(contact_id=contact_id)

        search = (request.query_params.get('search') or '').strip()
        if search:
            deals = deals.filter(
                Q(title__icontains=search)
                | Q(contact__fullname__icontains=search)
                | Q(contact__email__icontains=search)
                | Q(contact__company__icontains=search)
            ).distinct()

        sort_by = request.query_params.get('sort_by', 'created_at')
        order = request.query_params.get('order', 'desc')
        if order == 'desc':
            sort_by = f'-{sort_by}'
        deals = deals.order_by(sort_by)

        page, limit = self._parse_page_params(request)
        start = (page - 1) * limit
        end = start + limit
        total = deals.count()

        paginated_deals = deals[start:end]
        serialized_deals = DealSerializer(paginated_deals, many=True).data

        pipelines_data = {}
        pipelines = Pipeline.objects.filter(tenant=tenant, is_active=True).prefetch_related('stages')
        for pipeline in pipelines:
            stages_data = {}
            for stage in pipeline.stages.all():
                stage_deals = Deal.objects.filter(tenant=tenant, stage=stage)
                stages_data[stage.name] = {
                    'id': str(stage.id),
                    'count': stage_deals.count(),
                    'value': float(stage_deals.aggregate(total=Sum('value'))['total'] or 0)
                }
            pipelines_data[pipeline.name] = {
                'id': str(pipeline.id),
                'stages': stages_data
            }

        stats = Deal.objects.filter(tenant=tenant).aggregate(
            total_value=Sum('value'),
            total_count=Count('id'),
            open_count=Count('id', filter=Q(status=DealStatusChoices.OPEN)),
            won_count=Count('id', filter=Q(status=DealStatusChoices.WON)),
            lost_count=Count('id', filter=Q(status=DealStatusChoices.LOST)),
            won_value=Sum('value', filter=Q(status=DealStatusChoices.WON)),
        )

        pagination = {
            "current_page": page,
            "total_pages": (total + limit - 1) // limit if limit else 1,
            "total_items": total,
            "items_per_page": limit,
        }

        response = {
            "deals": serialized_deals,
            "pipelines": pipelines_data,
            "stats": {
                "total_value": float(stats['total_value'] or 0),
                "total_count": stats['total_count'] or 0,
                "open_count": stats['open_count'] or 0,
                "won_count": stats['won_count'] or 0,
                "lost_count": stats['lost_count'] or 0,
                "won_value": float(stats['won_value'] or 0),
            },
            "pagination": pagination,
        }
        return Response(response)

    def post(self, request):
        tenant = self._get_tenant(request)
        serializer = DealCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        deal = serializer.save(tenant=tenant, created_by=request.user)
        
        emit_event(
            name="deal.created",
            tenant_id=tenant.tenant_code,
            actor={"type": "user", "id": str(request.user.id)},
            entity={"type": "deal", "id": str(deal.id)},
            payload={
                "deal_id": str(deal.id),
                "title": deal.title,
                # Backwards-compatible aliases for older flows / event defs.
                "name": deal.title,
                "deal_name": deal.title,
                "description": deal.description,
                "value": float(deal.value),
                # Backwards-compatible alias.
                "deal_value": float(deal.value),
                "currency": getattr(deal, "currency", None),
                "contact_id": str(deal.contact_id) if deal.contact_id else None,
                "pipeline_id": str(deal.pipeline_id) if deal.pipeline_id else None,
                "pipeline_name": deal.pipeline.name if deal.pipeline else None,
                "stage_id": str(deal.stage_id) if deal.stage_id else None,
                "stage_name": deal.stage.name if deal.stage else None,
                "status": deal.status,
                # Actionable snapshots
                "deal": snapshot_deal(deal, include_contact=True),
                "contact": snapshot_contact(deal.contact) if deal.contact else None,
            },
            source="api",
        )
        
        return Response(DealSerializer(deal).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["deals"])
class DealDetailView(PaginationMixin, ProtectedAPIView):
    def get(self, request, deal_id):
        tenant = self._get_tenant(request)
        try:
            deal = Deal.objects.select_related(
                'contact', 'pipeline', 'stage', 'owner', 'created_by'
            ).get(id=deal_id, tenant=tenant)
        except Deal.DoesNotExist:
            return Response({"error": "Deal not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(DealSerializer(deal).data)

    def patch(self, request, deal_id):
        """Partial update; delegates to put (serializer already uses partial=True)."""
        return self.put(request, deal_id)

    def put(self, request, deal_id):
        tenant = self._get_tenant(request)
        try:
            deal = Deal.objects.get(id=deal_id, tenant=tenant)
        except Deal.DoesNotExist:
            return Response({"error": "Deal not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = DealUpdateSerializer(deal, data=request.data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from moio_platform.core.events.emitter import serialize_value
        validated = dict(serializer.validated_data or {})
        previous_values = {}
        for field_name, new_value in validated.items():
            try:
                old_value = getattr(deal, field_name)
            except Exception:
                old_value = None
            if hasattr(old_value, "id"):
                old_value = getattr(old_value, "id", None)
            if hasattr(new_value, "id"):
                new_value = getattr(new_value, "id", None)
            previous_values[field_name] = serialize_value(old_value)

        serializer.save()

        new_values = {}
        changed_fields = []
        for field_name, _new_value in validated.items():
            try:
                cur_value = getattr(deal, field_name)
            except Exception:
                cur_value = None
            if hasattr(cur_value, "id"):
                cur_value = getattr(cur_value, "id", None)
            new_values[field_name] = serialize_value(cur_value)
            if previous_values.get(field_name) != new_values.get(field_name):
                changed_fields.append(field_name)

        if changed_fields:
            try:
                emit_event(
                    name="deal.updated",
                    tenant_id=tenant.tenant_code,
                    actor={"type": "user", "id": str(request.user.id)},
                    entity={"type": "deal", "id": str(deal.id)},
                    payload={
                        "deal_id": str(deal.id),
                        "changed_fields": changed_fields,
                        "previous_values": previous_values,
                        "new_values": new_values,
                        "deal": snapshot_deal(deal, include_contact=True),
                        "contact": snapshot_contact(deal.contact) if deal.contact else None,
                    },
                    source="api",
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "deal.updated event emission failed (deal save succeeded): %s", e, exc_info=True
                )
        return Response(DealSerializer(deal).data)

    def delete(self, request, deal_id):
        tenant = self._get_tenant(request)
        try:
            deal = Deal.objects.get(id=deal_id, tenant=tenant)
        except Deal.DoesNotExist:
            return Response({"error": "Deal not found"}, status=status.HTTP_404_NOT_FOUND)

        deal.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["deals"])
class DealMoveStageView(PaginationMixin, ProtectedAPIView):
    def post(self, request, deal_id):
        tenant = self._get_tenant(request)
        try:
            deal = Deal.objects.get(id=deal_id, tenant=tenant)
        except Deal.DoesNotExist:
            return Response({"error": "Deal not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = DealStageUpdateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        stage = serializer.validated_data['stage_id']
        if deal.pipeline and stage.pipeline_id != deal.pipeline_id:
            return Response(
                {"error": "Stage must belong to the deal's pipeline"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from_stage_name = deal.stage.name if deal.stage else None
        to_stage_name = stage.name

        comment_text = serializer.validated_data.get('comment')
        if comment_text:
            deal.add_comment(
                text=comment_text,
                author=request.user,
                comment_type="stage_change",
                from_stage=from_stage_name,
                to_stage=to_stage_name
            )

        from_stage_id = str(deal.stage_id) if deal.stage_id else None
        deal.stage = stage
        deal.save()
        
        emit_event(
            name="deal.stage_changed",
            tenant_id=tenant.tenant_code,
            actor={"type": "user", "id": str(request.user.id)},
            entity={"type": "deal", "id": str(deal.id)},
            payload={
                "deal_id": str(deal.id),
                "title": deal.title,
                # Backwards-compatible aliases for older flows / event defs.
                "name": deal.title,
                "deal_name": deal.title,
                "description": deal.description,
                "contact_id": str(deal.contact_id) if deal.contact_id else None,
                "from_stage_id": from_stage_id,
                "from_stage_name": from_stage_name,
                "to_stage_id": str(stage.id),
                "to_stage_name": to_stage_name,
                "pipeline_id": str(deal.pipeline_id) if deal.pipeline_id else None,
                "pipeline_name": deal.pipeline.name if deal.pipeline else None,
                # Canonical + alias for deal amount.
                "value": float(deal.value),
                "deal_value": float(deal.value),
                "currency": getattr(deal, "currency", None),
                "deal": snapshot_deal(deal, include_contact=True),
                "contact": snapshot_contact(deal.contact) if deal.contact else None,
            },
            source="api",
        )

        # If the new stage implies won/lost, emit the corresponding lifecycle event too.
        # Note: Deal.save() derives status from stage flags (see crm.models.Deal.save()).
        try:
            if getattr(stage, "is_won_stage", False):
                emit_event(
                    name="deal.won",
                    tenant_id=tenant.tenant_code,
                    actor={"type": "user", "id": str(request.user.id)},
                    entity={"type": "deal", "id": str(deal.id)},
                    payload={
                        "deal_id": str(deal.id),
                        "title": deal.title,
                        "name": deal.title,
                        "deal_name": deal.title,
                        "value": float(deal.value),
                        "deal_value": float(deal.value),
                        "currency": getattr(deal, "currency", None),
                        "won_by": str(request.user.id),
                        "contact_id": str(deal.contact_id) if deal.contact_id else None,
                        "deal": snapshot_deal(deal, include_contact=True),
                        "contact": snapshot_contact(deal.contact) if deal.contact else None,
                    },
                    source="api",
                )
            elif getattr(stage, "is_lost_stage", False):
                emit_event(
                    name="deal.lost",
                    tenant_id=tenant.tenant_code,
                    actor={"type": "user", "id": str(request.user.id)},
                    entity={"type": "deal", "id": str(deal.id)},
                    payload={
                        "deal_id": str(deal.id),
                        "title": deal.title,
                        "name": deal.title,
                        "deal_name": deal.title,
                        "value": float(deal.value),
                        "deal_value": float(deal.value),
                        "currency": getattr(deal, "currency", None),
                        "lost_reason": getattr(deal, "lost_reason", None) or None,
                        "competitor": None,
                        "contact_id": str(deal.contact_id) if deal.contact_id else None,
                        "deal": snapshot_deal(deal, include_contact=True),
                        "contact": snapshot_contact(deal.contact) if deal.contact else None,
                    },
                    source="api",
                )
        except Exception:
            # Never break the stage-change API due to event emission issues.
            pass
        
        return Response(DealSerializer(deal).data)


@extend_schema(tags=["deals"])
class DealCommentsView(PaginationMixin, ProtectedAPIView):
    def get(self, request, deal_id):
        tenant = self._get_tenant(request)
        try:
            deal = Deal.objects.get(id=deal_id, tenant=tenant)
        except Deal.DoesNotExist:
            return Response({"error": "Deal not found"}, status=status.HTTP_404_NOT_FOUND)

        comments = deal.comments if isinstance(deal.comments, list) else []
        comments_sorted = sorted(comments, key=lambda x: x.get('created_at', ''), reverse=True)

        return Response({
            "deal_id": str(deal.id),
            "comments": comments_sorted,
            "count": len(comments_sorted)
        })

    def post(self, request, deal_id):
        tenant = self._get_tenant(request)
        try:
            deal = Deal.objects.get(id=deal_id, tenant=tenant)
        except Deal.DoesNotExist:
            return Response({"error": "Deal not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = DealCommentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        comment = deal.add_comment(
            text=serializer.validated_data['text'],
            author=request.user,
            comment_type=serializer.validated_data.get('type', 'general')
        )
        deal.save()

        return Response({"comment": comment}, status=status.HTTP_201_CREATED)


@extend_schema(tags=["pipelines"])
class PipelinesView(PaginationMixin, ProtectedAPIView):
    DEFAULT_PAGE_SIZE = 50

    def get(self, request):
        tenant = self._get_tenant(request)
        pipelines = Pipeline.objects.filter(tenant=tenant).prefetch_related('stages')

        active_only = request.query_params.get('active', 'true').lower() == 'true'
        if active_only:
            pipelines = pipelines.filter(is_active=True)

        serialized = PipelineSerializer(pipelines, many=True).data
        return Response({"pipelines": serialized})

    def post(self, request):
        tenant = self._get_tenant(request)
        serializer = PipelineCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        pipeline = serializer.save(tenant=tenant)
        return Response(PipelineSerializer(pipeline).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["pipelines"])
class PipelineDetailView(PaginationMixin, ProtectedAPIView):
    def get(self, request, pipeline_id):
        tenant = self._get_tenant(request)
        try:
            pipeline = Pipeline.objects.prefetch_related('stages').get(id=pipeline_id, tenant=tenant)
        except Pipeline.DoesNotExist:
            return Response({"error": "Pipeline not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(PipelineSerializer(pipeline).data)

    def put(self, request, pipeline_id):
        tenant = self._get_tenant(request)
        try:
            pipeline = Pipeline.objects.get(id=pipeline_id, tenant=tenant)
        except Pipeline.DoesNotExist:
            return Response({"error": "Pipeline not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PipelineCreateSerializer(pipeline, data=request.data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(PipelineSerializer(pipeline).data)

    def delete(self, request, pipeline_id):
        tenant = self._get_tenant(request)
        try:
            pipeline = Pipeline.objects.get(id=pipeline_id, tenant=tenant)
        except Pipeline.DoesNotExist:
            return Response({"error": "Pipeline not found"}, status=status.HTTP_404_NOT_FOUND)

        pipeline.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["pipelines"])
class PipelineStagesView(PaginationMixin, ProtectedAPIView):
    def get(self, request, pipeline_id):
        tenant = self._get_tenant(request)
        try:
            pipeline = Pipeline.objects.get(id=pipeline_id, tenant=tenant)
        except Pipeline.DoesNotExist:
            return Response({"error": "Pipeline not found"}, status=status.HTTP_404_NOT_FOUND)

        stages = pipeline.stages.all().order_by('order')
        serialized = PipelineStageSerializer(stages, many=True).data
        return Response({"stages": serialized})

    def post(self, request, pipeline_id):
        tenant = self._get_tenant(request)
        try:
            pipeline = Pipeline.objects.get(id=pipeline_id, tenant=tenant)
        except Pipeline.DoesNotExist:
            return Response({"error": "Pipeline not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PipelineStageSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        stage = serializer.save(tenant=tenant, pipeline=pipeline)
        return Response(PipelineStageSerializer(stage).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["pipelines"])
class PipelineStageDetailView(PaginationMixin, ProtectedAPIView):
    def put(self, request, pipeline_id, stage_id):
        tenant = self._get_tenant(request)
        try:
            stage = PipelineStage.objects.get(
                id=stage_id, pipeline_id=pipeline_id, tenant=tenant
            )
        except PipelineStage.DoesNotExist:
            return Response({"error": "Stage not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PipelineStageSerializer(stage, data=request.data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(PipelineStageSerializer(stage).data)

    def delete(self, request, pipeline_id, stage_id):
        tenant = self._get_tenant(request)
        try:
            stage = PipelineStage.objects.get(
                id=stage_id, pipeline_id=pipeline_id, tenant=tenant
            )
        except PipelineStage.DoesNotExist:
            return Response({"error": "Stage not found"}, status=status.HTTP_404_NOT_FOUND)

        stage.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["pipelines"])
class PipelineCreateDefaultView(PaginationMixin, ProtectedAPIView):
    def post(self, request):
        tenant = self._get_tenant(request)

        existing = Pipeline.objects.filter(tenant=tenant).exists()
        if existing:
            return Response(
                {"error": "Pipelines already exist for this tenant"},
                status=status.HTTP_400_BAD_REQUEST
            )

        pipeline = Pipeline.objects.create(
            tenant=tenant,
            name="Sales Pipeline",
            description="Default sales pipeline",
            is_default=True
        )

        default_stages = [
            {"name": "Qualification", "order": 1, "probability": 10, "color": "#94a3b8"},
            {"name": "Proposal", "order": 2, "probability": 30, "color": "#60a5fa"},
            {"name": "Negotiation", "order": 3, "probability": 60, "color": "#fbbf24"},
            {"name": "Won", "order": 4, "probability": 100, "is_won_stage": True, "color": "#22c55e"},
            {"name": "Lost", "order": 5, "probability": 0, "is_lost_stage": True, "color": "#ef4444"},
        ]

        for stage_data in default_stages:
            PipelineStage.objects.create(
                tenant=tenant,
                pipeline=pipeline,
                **stage_data
            )

        return Response(
            PipelineSerializer(pipeline).data,
            status=status.HTTP_201_CREATED
        )
