"""
API Views for EventDefinition and EventLog management.

Provides endpoints for listing and retrieving event definitions
and event logs for flow triggers and audit purposes.
"""

import logging
import uuid
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from .models import EventDefinition, EventLog
from moio_platform.core.events.schemas import get_event_payload_schema
from moio_platform.core.events.schemas import EVENT_PAYLOAD_SCHEMAS

logger = logging.getLogger(__name__)


class EventDefinitionViewSet(ViewSet):
    """
    ViewSet for listing and retrieving event definitions.
    
    Endpoints:
    - GET /api/v1/flows/events/ - List all active event definitions
    - GET /api/v1/flows/events/{id}/ - Get event definition details
    """
    
    permission_classes = [IsAuthenticated]
    
    def _serialize_event_definition(self, event_def):
        """Serialize an EventDefinition to dict."""
        # Use canonical code-defined schemas for the flow contract.
        payload_schema = event_def.payload_schema
        is_canonical = False
        try:
            payload_schema = get_event_payload_schema(event_def.name)
            is_canonical = True
        except KeyError:
            # If not in canonical mapping, treat as unavailable under strict contract.
            payload_schema = {}
        return {
            'id': str(event_def.id),
            'name': event_def.name,
            'label': event_def.label,
            'description': event_def.description,
            'entity_type': event_def.entity_type,
            'category': event_def.category,
            'payload_schema': payload_schema,
            'hints': event_def.hints,
            'active': event_def.active,
            # Discovery flags: canonical events are emittable under strict contract.
            'is_canonical': is_canonical,
            'is_emittable': bool(is_canonical),
            'created_at': event_def.created_at.isoformat(),
            'updated_at': event_def.updated_at.isoformat(),
        }
    
    def list(self, request):
        """List all active event definitions."""
        category = request.query_params.get('category')
        entity_type = request.query_params.get('entity_type')
        include_inactive = request.query_params.get('include_inactive', 'false').lower() == 'true'
        
        queryset = EventDefinition.objects.all()
        
        if not include_inactive:
            queryset = queryset.filter(active=True)
        
        if category:
            queryset = queryset.filter(category=category)
        
        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)
        
        queryset = queryset.order_by('category', 'name')
        
        events = [self._serialize_event_definition(e) for e in queryset]
        by_name = {e.get("name"): e for e in events if e.get("name")}

        # Include canonical-only events (code-defined) so the builder can use them
        # without requiring DB seed migrations.
        for name in sorted(EVENT_PAYLOAD_SCHEMAS.keys()):
            if name in by_name:
                continue
            entity_type = name.split(".", 1)[0] if "." in name else "event"
            category = "crm" if entity_type in {"deal", "ticket", "contact"} else (
                "campaigns" if entity_type == "campaign" else (
                    "chatbot" if entity_type in {"message", "chatbot_session"} else "other"
                )
            )
            now = timezone.now().isoformat()
            by_name[name] = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"moio.event.{name}")),
                "name": name,
                "label": name.replace(".", " ").replace("_", " ").title(),
                "description": "",
                "entity_type": entity_type,
                "category": category,
                "payload_schema": get_event_payload_schema(name),
                "hints": {},
                "active": True,
                "is_canonical": True,
                "is_emittable": True,
                "created_at": now,
                "updated_at": now,
            }

        events = list(by_name.values())
        
        categories = list(
            EventDefinition.objects.filter(active=True)
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        # Merge categories with canonical ones.
        categories = sorted({*(c for c in categories if c), *(e.get("category") for e in events if e.get("category"))})
        
        entity_types = list(
            EventDefinition.objects.filter(active=True)
            .values_list('entity_type', flat=True)
            .distinct()
            .order_by('entity_type')
        )
        entity_types = sorted({*entity_types, *(e.get("entity_type") for e in events if e.get("entity_type"))})
        
        return Response({
            'events': events,
            'count': len(events),
            'categories': [c for c in categories if c],
            'entity_types': entity_types,
        })
    
    def retrieve(self, request, pk=None):
        """Get event definition details."""
        try:
            event_def = EventDefinition.objects.get(pk=pk)
        except EventDefinition.DoesNotExist:
            return Response(
                {'error': 'Event definition not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'event': self._serialize_event_definition(event_def),
        })


class EventLogViewSet(ViewSet):
    """
    ViewSet for listing and retrieving event logs.
    
    Endpoints:
    - GET /api/v1/flows/event-logs/ - List event logs with filtering
    - GET /api/v1/flows/event-logs/{id}/ - Get event log details
    """
    
    permission_classes = [IsAuthenticated]
    
    def _serialize_event_log(self, event_log):
        """Serialize an EventLog to dict."""
        return {
            'id': str(event_log.id),
            'name': event_log.name,
            'tenant_id': str(event_log.tenant_id),
            'actor': event_log.actor,
            'entity': event_log.entity,
            'payload': event_log.payload,
            'occurred_at': event_log.occurred_at.isoformat(),
            'created_at': event_log.created_at.isoformat(),
            'correlation_id': str(event_log.correlation_id) if event_log.correlation_id else None,
            'source': event_log.source,
            'routed': event_log.routed,
            'routed_at': event_log.routed_at.isoformat() if event_log.routed_at else None,
            'flow_executions': event_log.flow_executions,
        }
    
    def list(self, request):
        """
        List event logs with optional filtering.
        
        Query params:
        - name: Filter by event name (exact match)
        - entity_type: Filter by entity type
        - entity_id: Filter by entity ID
        - routed: Filter by routed status (true/false)
        - limit: Number of results (default 50, max 200)
        - offset: Pagination offset
        """
        tenant = getattr(request.user, 'tenant', None)
        if not tenant:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        name = request.query_params.get('name')
        entity_type = request.query_params.get('entity_type')
        entity_id = request.query_params.get('entity_id')
        routed = request.query_params.get('routed')
        limit = min(int(request.query_params.get('limit', 50)), 200)
        offset = int(request.query_params.get('offset', 0))
        
        queryset = EventLog.objects.filter(tenant_id=tenant.tenant_code)
        
        if name:
            queryset = queryset.filter(name=name)
        
        if entity_type:
            queryset = queryset.filter(entity__type=entity_type)
        
        if entity_id:
            queryset = queryset.filter(entity__id=entity_id)
        
        if routed is not None:
            routed_bool = routed.lower() == 'true'
            queryset = queryset.filter(routed=routed_bool)
        
        total = queryset.count()
        queryset = queryset.order_by('-occurred_at')[offset:offset + limit]
        
        logs = [self._serialize_event_log(log) for log in queryset]
        
        return Response({
            'logs': logs,
            'count': len(logs),
            'total': total,
            'limit': limit,
            'offset': offset,
        })
    
    def retrieve(self, request, pk=None):
        """Get event log details."""
        tenant = getattr(request.user, 'tenant', None)
        if not tenant:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            event_log = EventLog.objects.get(pk=pk, tenant_id=tenant.tenant_code)
        except EventLog.DoesNotExist:
            return Response(
                {'error': 'Event log not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'log': self._serialize_event_log(event_log),
        })
