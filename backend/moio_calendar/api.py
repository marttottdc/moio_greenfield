"""
Calendar API endpoints using Django REST Framework.
"""

import logging
import uuid
from datetime import datetime, timedelta

from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response

from moio_calendar.models import (
    Calendar, CalendarEvent, AvailabilitySlot, SharedResource,
    ResourceBooking, BookingType, EventAttendee, CalendarPermission as CalendarPermissionModel,
    CalendarVisibility, EventStatus
)
from .services.validation_service import CalendarValidationService, CalendarValidationError
from .security import (
    CalendarPermission as CalendarAccessPermission, CalendarThrottle, StrictCalendarThrottle,
    PublicBookingThrottle, InputSanitizer, SecurityMiddleware
)
from .performance import (
    CalendarCache, QueryOptimizer, PerformanceMiddleware, monitor_performance
)
from .monitoring import (
    CalendarMonitor, ErrorTracker, PerformanceTracker, monitor_api_performance
)

logger = logging.getLogger(__name__)


class CalendarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Calendar
        fields = ['id', 'name', 'description', 'visibility', 'color', 'is_default',
                 'owner', 'allowed_users', 'created_at', 'updated_at']
        read_only_fields = ['owner', 'created_at', 'updated_at']

    def validate(self, data):
        """Ensure only calendar owner can modify certain fields."""
        if self.instance and self.context['request'].user != self.instance.owner:
            # Non-owners cannot change visibility or make calendar default
            if 'visibility' in data and data['visibility'] != self.instance.visibility:
                raise serializers.ValidationError("Only calendar owner can change visibility")
            if 'is_default' in data and data['is_default'] != self.instance.is_default:
                raise serializers.ValidationError("Only calendar owner can change default status")
        return data


class CalendarPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarPermissionModel
        fields = ['id', 'calendar', 'user', 'can_edit', 'added_at']
        read_only_fields = ['added_at']


class EventAttendeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventAttendee
        fields = ['id', 'event', 'user', 'status', 'added_at']


class CalendarEventSerializer(serializers.ModelSerializer):
    attendees = EventAttendeeSerializer(many=True, read_only=True)
    duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = CalendarEvent
        fields = ['id', 'calendar', 'title', 'description', 'start_time', 'end_time',
                 'event_type', 'status', 'organizer', 'attendees', 'external_attendee_name',
                 'external_attendee_email', 'external_attendee_phone', 'location',
                 'meeting_link', 'is_public', 'booking_link', 'duration_minutes',
                 'created_at', 'updated_at']
        read_only_fields = ['organizer', 'booking_link', 'created_at', 'updated_at']

    def get_duration_minutes(self, obj):
        if obj.start_time and obj.end_time:
            duration = obj.end_time - obj.start_time
            return int(duration.total_seconds() // 60)
        return None

    def validate(self, data):
        """Business logic validation for events."""
        start_time = data.get('start_time') or getattr(self.instance, 'start_time', None)
        end_time = data.get('end_time') or getattr(self.instance, 'end_time', None)
        calendar = data.get('calendar') or getattr(self.instance, 'calendar', None)
        user = self.context['request'].user
        exclude_event_id = str(self.instance.id) if self.instance else None

        if start_time and end_time and calendar:
            try:
                CalendarValidationService.validate_event_creation(
                    calendar=calendar,
                    start_time=start_time,
                    end_time=end_time,
                    exclude_event_id=exclude_event_id,
                    user=user
                )
            except CalendarValidationError as e:
                raise serializers.ValidationError(str(e))

        return data

    def create(self, validated_data):
        if not validated_data.get('booking_link'):
            validated_data['booking_link'] = f"event-{uuid.uuid4().hex}"
        return super().create(validated_data)


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilitySlot
        fields = ['id', 'calendar', 'day_of_week', 'start_time', 'end_time',
                 'slot_duration', 'is_active', 'created_at']
        read_only_fields = ['created_at']


class SharedResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SharedResource
        fields = ['id', 'calendar', 'name', 'description', 'resource_type', 'capacity',
                 'location', 'advance_booking_days', 'min_booking_duration',
                 'max_booking_duration', 'is_active', 'created_at']
        read_only_fields = ['created_at']


class ResourceBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceBooking
        fields = ['id', 'calendar', 'resource', 'event', 'start_time', 'end_time',
                 'booked_by', 'status', 'created_at']
        read_only_fields = ['booked_by', 'created_at']


class BookingTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingType
        fields = ['id', 'calendar', 'name', 'description', 'duration', 'buffer_time_before',
                 'buffer_time_after', 'advance_booking_days', 'booking_slug', 'is_active',
                 'created_at']
        read_only_fields = ['created_at']


class CalendarViewSet(viewsets.ModelViewSet):
    serializer_class = CalendarSerializer
    permission_classes = [permissions.IsAuthenticated, CalendarAccessPermission]
    throttle_classes = [CalendarThrottle]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['visibility', 'is_default']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['-is_default', 'name']

    def get_queryset(self):
        return Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='public', tenant=self.request.tenant) |
            models.Q(visibility='team', tenant=self.request.tenant) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        # If this is the first calendar for the user, make it default
        if not Calendar.objects.filter(owner=self.request.user).exists():
            serializer.save(owner=self.request.user, tenant=self.request.tenant, is_default=True)
        else:
            serializer.save(owner=self.request.user, tenant=self.request.tenant)

    @action(detail=True, methods=['post'], throttle_classes=[StrictCalendarThrottle])
    def share(self, request, pk=None):
        """Share calendar with other users."""
        calendar = self.get_object()
        if calendar.owner != request.user:
            SecurityMiddleware.log_security_event(
                'unauthorized_calendar_share_attempt',
                request.user,
                {'calendar_id': str(calendar.id)}
            )
            return Response({'error': 'Only calendar owner can share'}, status=403)

        user_ids = request.data.get('user_ids', [])
        can_edit = request.data.get('can_edit', False)

        # Sanitize inputs
        user_ids = [str(uid).strip() for uid in user_ids if uid]
        can_edit = bool(can_edit)

        # Validate sharing permissions
        try:
            for user_id in user_ids[:10]:  # Limit to 10 users at once
                from django.contrib.auth import get_user_model
                User = get_user_model()
                target_user = User.objects.get(id=user_id)

                CalendarValidationService.validate_calendar_sharing(
                    calendar=calendar,
                    target_user=target_user,
                    can_edit=can_edit,
                    requesting_user=request.user
                )
        except Exception as e:
            return Response({'error': str(e)}, status=400)

        created_count = 0
        for user_id in user_ids[:10]:  # Limit to 10 users
            _, created = CalendarPermissionModel.objects.get_or_create(
                calendar=calendar,
                user_id=user_id,
                defaults={'can_edit': can_edit}
            )
            if created:
                created_count += 1

        SecurityMiddleware.log_security_event(
            'calendar_shared',
            request.user,
            {'calendar_id': str(calendar.id), 'shared_count': created_count}
        )

        return Response({
            'message': f'Calendar shared with {created_count} users',
            'shared_count': created_count
        })

    @action(detail=True, methods=['post'])
    def unshare(self, request, pk=None):
        """Remove sharing permissions for users."""
        calendar = self.get_object()
        if calendar.owner != request.user:
            return Response({'error': 'Only calendar owner can manage sharing'}, status=403)

        user_ids = request.data.get('user_ids', [])
        deleted_count = CalendarPermissionModel.objects.filter(
            calendar=calendar,
            user_id__in=user_ids
        ).delete()[0]

        return Response({
            'message': f'Removed sharing for {deleted_count} users',
            'removed_count': deleted_count
        })

    @action(detail=True, methods=['get'])
    def permissions(self, request, pk=None):
        """Get sharing permissions for this calendar."""
        calendar = self.get_object()
        if calendar.owner != request.user and not calendar.can_edit(request.user):
            return Response({'error': 'Permission denied'}, status=403)

        permissions = CalendarPermissionModel.objects.filter(calendar=calendar).select_related('user')
        data = [{
            'user_id': p.user.id,
            'user_email': p.user.email,
            'user_name': p.user.get_full_name() or p.user.username,
            'can_edit': p.can_edit,
            'added_at': p.added_at
        } for p in permissions]

        return Response({'permissions': data})

    @action(detail=False, methods=['get'])
    def my_calendars(self, request):
        """Get only calendars owned by current user."""
        calendars = self.get_queryset().filter(owner=request.user)
        serializer = self.get_serializer(calendars, many=True)
        return Response(serializer.data)


class CalendarEventViewSet(viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    permission_classes = [permissions.IsAuthenticated, CalendarAccessPermission]
    throttle_classes = [CalendarThrottle]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['calendar', 'event_type', 'status', 'start_time', 'end_time']
    search_fields = ['title', 'description', 'location']
    ordering_fields = ['start_time', 'end_time', 'created_at', 'title']
    ordering = ['-start_time']

    def get_queryset(self):
        # Use optimized query to get user calendars
        user_calendars = QueryOptimizer.get_calendar_with_permissions(self.request.user)
        calendar_ids = list(user_calendars.values_list('id', flat=True))

        queryset = QueryOptimizer.get_events_for_calendars(
            calendar_ids=calendar_ids,
            start_date=self.request.query_params.get('start_date'),
            end_date=self.request.query_params.get('end_date')
        )

        return queryset.select_related('calendar', 'organizer')

    @monitor_api_performance("calendar_events")
    def list(self, request, *args, **kwargs):
        """Override list to add comprehensive monitoring."""
        return super().list(request, *args, **kwargs)

    @monitor_api_performance("calendar_event_create")
    def create(self, request, *args, **kwargs):
        """Override create to add comprehensive monitoring."""
        response = super().create(request, *args, **kwargs)

        # Invalidate relevant caches
        if hasattr(response, 'data') and 'calendar' in response.data:
            CalendarCache.invalidate_availability_cache(response.data['calendar'])

        # Log business event
        CalendarMonitor.log_business_event(
            'event_created',
            calendar_id=response.data.get('calendar'),
            event_id=response.data.get('id'),
            user_id=str(request.user.id)
        )

        return response

    def perform_create(self, serializer):
        # Check calendar permissions
        calendar = serializer.validated_data['calendar']
        if not calendar.can_edit(self.request.user):
            raise serializers.ValidationError('You do not have permission to create events in this calendar')

        event = serializer.save(organizer=self.request.user, tenant=self.request.tenant)

        # Invalidate availability cache for this calendar
        CalendarCache.invalidate_availability_cache(str(calendar.id))

        return event

    def perform_update(self, serializer):
        # Check calendar permissions
        calendar = serializer.instance.calendar
        if not calendar.can_edit(self.request.user):
            raise serializers.ValidationError('You do not have permission to edit events in this calendar')

        event = serializer.save()

        # Invalidate availability cache for this calendar
        CalendarCache.invalidate_availability_cache(str(calendar.id))

        return event

    def perform_destroy(self, instance):
        # Check calendar permissions
        if not instance.calendar.can_edit(self.request.user):
            raise serializers.ValidationError('You do not have permission to delete events in this calendar')

        calendar_id = str(instance.calendar.id)
        instance.delete()

        # Invalidate availability cache for this calendar
        CalendarCache.invalidate_availability_cache(calendar_id)

    @action(detail=True, methods=['post'])
    def add_attendee(self, request, pk=None):
        """Add an attendee to an event."""
        event = self.get_object()
        if not event.calendar.can_edit(request.user):
            return Response({'error': 'Permission denied'}, status=403)

        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id required'}, status=400)

        attendee, created = EventAttendee.objects.get_or_create(
            event=event,
            user_id=user_id,
            defaults={'status': 'pending'}
        )

        serializer = EventAttendeeSerializer(attendee)
        return Response(serializer.data, status=201 if created else 200)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update event status."""
        event = self.get_object()
        if not event.calendar.can_edit(request.user):
            return Response({'error': 'Permission denied'}, status=403)

        new_status = request.data.get('status')
        if new_status not in dict(EventStatus.choices):
            return Response({'error': 'Invalid status'}, status=400)

        event.status = new_status
        event.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(event)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming events for the next 30 days."""
        end_date = timezone.now() + timedelta(days=30)
        queryset = self.get_queryset().filter(
            start_time__gte=timezone.now(),
            start_time__lte=end_date
        )[:50]  # Limit results

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class AvailabilitySlotViewSet(viewsets.ModelViewSet):
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user_calendars = Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()

        return AvailabilitySlot.objects.filter(calendar__in=user_calendars)

    def perform_create(self, serializer):
        calendar = serializer.validated_data['calendar']
        if not calendar.can_edit(self.request.user):
            raise serializers.ValidationError('You do not have permission to manage availability for this calendar')

        serializer.save(tenant=self.request.tenant)


class SharedResourceViewSet(viewsets.ModelViewSet):
    serializer_class = SharedResourceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user_calendars = Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()

        return SharedResource.objects.filter(calendar__in=user_calendars)

    def perform_create(self, serializer):
        calendar = serializer.validated_data['calendar']
        if not calendar.can_edit(self.request.user):
            raise serializers.ValidationError('You do not have permission to manage resources for this calendar')

        serializer.save(tenant=self.request.tenant)


class ResourceBookingViewSet(viewsets.ModelViewSet):
    serializer_class = ResourceBookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['calendar', 'resource', 'status', 'start_time', 'end_time']
    search_fields = ['resource__name']
    ordering_fields = ['start_time', 'end_time', 'created_at']
    ordering = ['-start_time']

    def get_queryset(self):
        user_calendars = Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()

        return ResourceBooking.objects.filter(calendar__in=user_calendars).select_related('resource', 'booked_by', 'calendar')

    def perform_create(self, serializer):
        calendar = serializer.validated_data['calendar']
        resource = serializer.validated_data['resource']
        start_time = serializer.validated_data['start_time']
        end_time = serializer.validated_data['end_time']
        user = self.request.user
        exclude_booking_id = None

        try:
            CalendarValidationService.validate_resource_booking(
                resource=resource,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=exclude_booking_id,
                user=user
            )
        except CalendarValidationError as e:
            raise serializers.ValidationError(str(e))

        serializer.save(booked_by=user, tenant=self.request.tenant)


class BookingTypeViewSet(viewsets.ModelViewSet):
    serializer_class = BookingTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['calendar', 'is_active']
    search_fields = ['name', 'description', 'booking_slug']
    ordering_fields = ['name', 'created_at', 'is_active']
    ordering = ['name']

    def get_queryset(self):
        user_calendars = Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()

        return BookingType.objects.filter(calendar__in=user_calendars).select_related('calendar')

    def perform_create(self, serializer):
        calendar = serializer.validated_data['calendar']
        booking_slug = serializer.validated_data.get('booking_slug')
        duration = serializer.validated_data.get('duration')
        user = self.request.user

        try:
            CalendarValidationService.validate_booking_type(
                calendar=calendar,
                booking_slug=booking_slug,
                duration=duration,
                user=user
            )
        except CalendarValidationError as e:
            raise serializers.ValidationError(str(e))

        serializer.save(tenant=self.request.tenant)

    @action(detail=True, methods=['get'])
    def public_url(self, request, pk=None):
        """Get the public booking URL for this booking type."""
        booking_type = self.get_object()
        if booking_type.calendar.visibility != 'public':
            return Response({'error': 'Booking type is not public'}, status=400)

        public_url = request.build_absolute_uri(
            f'/calendar/api/public/availability/{booking_type.booking_slug}/'
        )

        return Response({
            'public_url': public_url,
            'booking_slug': booking_type.booking_slug
        })


class EventAttendeeViewSet(viewsets.ModelViewSet):
    serializer_class = EventAttendeeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Get attendees for events in calendars the user can view
        user_calendars = Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='public', tenant=self.request.tenant) |
            models.Q(visibility='team', tenant=self.request.tenant) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()

        return EventAttendee.objects.filter(event__calendar__in=user_calendars)

    def perform_create(self, serializer):
        event = serializer.validated_data['event']
        if not event.calendar.can_edit(self.request.user):
            raise serializers.ValidationError('You do not have permission to manage attendees for this event')

        serializer.save()


# =============================================================================
# PUBLIC BOOKING API (No Authentication Required)
# =============================================================================

class PublicBookingSerializer(serializers.Serializer):
    """Serializer for public booking creation."""
    booking_slug = serializers.SlugField()
    selected_datetime = serializers.DateTimeField()
    external_name = serializers.CharField(max_length=100)
    external_email = serializers.EmailField()
    external_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_selected_datetime(self, value):
        """Validate that the selected time is in the future and available."""
        if value <= timezone.now():
            raise serializers.ValidationError("Cannot book appointments in the past")

        # Additional validation will be done in the view
        return value


class PublicBookingTypeSerializer(serializers.ModelSerializer):
    """Serializer for public booking type information."""
    calendar_name = serializers.CharField(source='calendar.name', read_only=True)
    organizer_name = serializers.SerializerMethodField()

    class Meta:
        model = BookingType
        fields = ['id', 'name', 'description', 'duration', 'booking_slug',
                 'calendar_name', 'organizer_name']

    def get_organizer_name(self, obj):
        return obj.calendar.owner.get_full_name() or obj.calendar.owner.username


class AvailableSlotSerializer(serializers.Serializer):
    """Serializer for available time slots."""
    datetime = serializers.DateTimeField()
    display_date = serializers.CharField()
    display_time = serializers.CharField()
    end_datetime = serializers.DateTimeField()


@api_view(['GET'])
@permission_classes([])
@throttle_classes([PublicBookingThrottle])
def public_booking_types(request):
    """Get all active public booking types."""
    # Security check - don't expose internal details
    SecurityMiddleware.check_request_sanity(request)

    booking_types = BookingType.objects.filter(
        is_active=True,
        calendar__visibility='public'
    ).select_related('calendar', 'calendar__owner')

    serializer = PublicBookingTypeSerializer(booking_types, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([])
@throttle_classes([PublicBookingThrottle])
def public_booking_availability(request, booking_slug):
    """Get available time slots for a booking type."""
    # Security check
    SecurityMiddleware.check_request_sanity(request)

    # Sanitize input
    booking_slug = InputSanitizer.sanitize_string(booking_slug, 100)

    try:
        booking_type = BookingType.objects.select_related('calendar').get(
            booking_slug=booking_slug,
            is_active=True,
            calendar__visibility='public'
        )
    except BookingType.DoesNotExist:
        return Response({'error': 'Booking type not found'}, status=404)

    # Check cache first
    cache_key = CalendarCache.get_availability_cache_key(
        str(booking_type.calendar.id),
        str(booking_type.id)
    )

    available_slots = CalendarCache.get_cached_availability(
        str(booking_type.calendar.id),
        str(booking_type.id)
    )

    if available_slots is None:
        # Calculate availability
        start_date = timezone.now().date()
        end_date = start_date + timedelta(days=booking_type.advance_booking_days)

        try:
            available_slots = CalendarValidationService.get_available_slots(
                calendar=booking_type.calendar,
                booking_type=booking_type,
                start_date=start_date,
                end_date=end_date
            )

            # Cache the result
            CalendarCache.cache_availability(
                str(booking_type.calendar.id),
                str(booking_type.id),
                available_slots
            )

        except Exception as e:
            logger.error(f"Error calculating availability for {booking_slug}: {e}")
            return Response({'error': 'Error calculating availability'}, status=500)

    return Response({'available_slots': available_slots})


@api_view(['POST'])
@permission_classes([])
@throttle_classes([PublicBookingThrottle])
def create_public_booking(request):
    """Create a public booking."""
    # Security check
    SecurityMiddleware.check_request_sanity(request)

    serializer = PublicBookingSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    booking_slug = InputSanitizer.sanitize_string(serializer.validated_data.get('booking_slug', ''))
    selected_datetime = serializer.validated_data['selected_datetime']
    external_name = InputSanitizer.sanitize_string(serializer.validated_data['external_name'])
    external_email = serializer.validated_data['external_email'].strip().lower()
    external_phone = InputSanitizer.sanitize_string(serializer.validated_data.get('external_phone', ''))

    # Additional validation
    if not InputSanitizer.validate_email(external_email):
        return Response({'error': 'Invalid email address'}, status=400)

    if external_phone and not InputSanitizer.validate_phone(external_phone):
        return Response({'error': 'Invalid phone number'}, status=400)

    try:
        with transaction.atomic():
            booking_type, calendar = CalendarValidationService.validate_public_booking(
                booking_slug=booking_slug,
                selected_datetime=selected_datetime,
                lock_calendar=True
            )

            event = CalendarEvent.objects.create(
                calendar=calendar,
                title=f"Booking: {booking_type.name}",
                description=f"Booked by {external_name} via public booking",
                start_time=selected_datetime,
                end_time=selected_datetime + booking_type.duration,
                event_type='appointment',
                status='confirmed',
                organizer=calendar.owner,
                external_attendee_name=external_name,
                external_attendee_email=external_email,
                external_attendee_phone=external_phone,
                is_public=True,
                booking_link=f"public-{uuid.uuid4().hex}",
                tenant=booking_type.tenant
            )

            SecurityMiddleware.log_security_event(
                'public_booking_created',
                None,  # No authenticated user
                {
                    'event_id': str(event.id),
                    'booking_type': booking_slug,
                    'external_email': external_email
                }
            )

    except CalendarValidationError as e:
        return Response({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error creating public booking: {e}")
        return Response({'error': 'Failed to create booking'}, status=500)

    return Response({
        'event_id': str(event.id),
        'message': 'Booking confirmed',
        'event_details': {
            'title': event.title,
            'start_time': event.start_time.isoformat(),
            'end_time': event.end_time.isoformat(),
            'location': event.location or '',
            'meeting_link': event.meeting_link or ''
        }
    }, status=201)