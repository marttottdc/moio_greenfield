"""
API views for CRM Views and queries.
"""
from __future__ import annotations

import logging
import uuid

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from datalab.crm_sources.models import CRMView
from datalab.crm_sources.services import CRMQueryEngine, CRMQueryEngineError
from datalab.api.views import AuthenticatedDataLabView

from . import serializers

logger = logging.getLogger(__name__)


class CRMViewViewSet(AuthenticatedDataLabView, viewsets.ReadOnlyModelViewSet):
    """ViewSet for CRM Views (list and retrieve)."""
    
    serializer_class = serializers.CRMViewSerializer
    lookup_field = 'key'
    lookup_url_kwarg = 'key'
    # Allow keys with dots (e.g. crm.contacts.with_deals); default DRF regex is [^/.]+
    lookup_value_regex = '[^/]+'
    
    def get_queryset(self):
        """Get CRMViews for current tenant (including global ones)."""
        tenant = self.get_tenant(self.request)
        from django.db.models import Q
        return CRMView.objects.filter(
            Q(tenant=tenant) | Q(is_global=True),
            is_active=True
        ).order_by('key')
    
    def get_object(self):
        """Get object by key or by id (UUID from list)."""
        lookup_value = self.kwargs.get(self.lookup_url_kwarg)
        if lookup_value is None:
            return super().get_object()

        tenant = self.get_tenant(self.request)
        from django.db.models import Q

        # Allow retrieval by key (e.g. 'crm.deals.active') or by id (UUID from list)
        def _get_by_key(key):
            return CRMView.objects.get(
                Q(tenant=tenant) | Q(is_global=True),
                key=key,
                is_active=True
            )

        def _get_by_pk(pk):
            return CRMView.objects.get(
                Q(tenant=tenant) | Q(is_global=True),
                pk=pk,
                is_active=True
            )

        try:
            if isinstance(lookup_value, uuid.UUID):
                obj = _get_by_pk(lookup_value)
            else:
                try:
                    parsed = uuid.UUID(str(lookup_value))
                    obj = _get_by_pk(parsed)
                except (ValueError, TypeError):
                    obj = _get_by_key(str(lookup_value))
            self.check_object_permissions(self.request, obj)
            return obj
        except CRMView.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound(f"CRM View with key or id '{lookup_value}' not found")
        except CRMView.MultipleObjectsReturned:
            obj = CRMView.objects.filter(
                Q(tenant=tenant) | Q(is_global=True),
                key=lookup_value,
                is_active=True
            ).first()
            if obj is None:
                from rest_framework.exceptions import NotFound
                raise NotFound(f"CRM View with key or id '{lookup_value}' not found")
            self.check_object_permissions(self.request, obj)
            return obj


class CRMQueryViewSet(AuthenticatedDataLabView, viewsets.ViewSet):
    """ViewSet for executing CRM queries."""
    
    query_engine = CRMQueryEngine()
    
    @action(detail=False, methods=['post'])
    def query(self, request):
        """Execute CRM query."""
        tenant = self.get_tenant(request)
        
        serializer = serializers.CRMQueryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        view_key = serializer.validated_data['view_key']
        filters = serializer.validated_data.get('filters', {})
        limit = serializer.validated_data.get('limit')
        materialize = serializer.validated_data.get('materialize', False)
        
        try:
            # Execute query
            resultset = self.query_engine.execute(
                view_key=view_key,
                tenant=tenant,
                filters=filters,
                limit=limit,
                materialize=materialize,
                user=request.user
            )
            
            response_data = {
                'resultset_id': resultset.id,
                'schema': resultset.schema_json,
                'row_count': resultset.row_count,
                'preview': resultset.preview_json,
            }
            
            response_serializer = serializers.CRMQueryResponseSerializer(data=response_data)
            response_serializer.is_valid(raise_exception=True)
            
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except CRMQueryEngineError as e:
            return Response(
                {'error': 'CRM query failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"CRM query error: {e}", exc_info=True)
            return Response(
                {'error': 'CRM query failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
