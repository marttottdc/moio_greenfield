"""
Performance optimizations for the calendar app.
Includes caching, query optimization, and background processing.
"""

from django.core.cache import cache
from django.db import connection
from django.db.models import Prefetch, Q
from django.utils import timezone
from functools import wraps
import hashlib
import json
import logging

from .models import Calendar, CalendarEvent, AvailabilitySlot, BookingType

logger = logging.getLogger(__name__)


class CalendarCache:
    """Caching utilities for calendar operations."""

    CALENDAR_PREFIX = "calendar:"
    AVAILABILITY_PREFIX = "availability:"
    AVAILABILITY_VERSION_PREFIX = "availability_version:"
    BOOKING_PREFIX = "booking:"

    @staticmethod
    def get_cache_key(prefix: str, *args) -> str:
        """Generate a consistent cache key."""
        key_data = ":".join(str(arg) for arg in args)
        return f"{prefix}{key_data}"

    @classmethod
    def get_calendar_cache_key(cls, calendar_id: str) -> str:
        """Cache key for calendar data."""
        return cls.get_cache_key(cls.CALENDAR_PREFIX, calendar_id)

    @classmethod
    def get_availability_cache_key(cls, calendar_id: str, booking_type_id: str = None) -> str:
        """Cache key for availability data."""
        version = cls._get_availability_version(calendar_id)
        if booking_type_id:
            return cls.get_cache_key(cls.AVAILABILITY_PREFIX, calendar_id, version, booking_type_id)
        return cls.get_cache_key(cls.AVAILABILITY_PREFIX, calendar_id, version)

    @classmethod
    def _get_availability_version(cls, calendar_id: str) -> int:
        """Get cache version for calendar availability keys."""
        version_key = cls.get_cache_key(cls.AVAILABILITY_VERSION_PREFIX, calendar_id)
        version = cache.get(version_key)
        if version is None:
            version = 1
            cache.set(version_key, version)
        return version

    @classmethod
    def cache_calendar(cls, calendar: Calendar, timeout: int = 600):
        """Cache calendar object with permissions."""
        key = cls.get_calendar_cache_key(str(calendar.id))
        data = {
            'id': str(calendar.id),
            'name': calendar.name,
            'visibility': calendar.visibility,
            'owner_id': str(calendar.owner.id),
            'color': calendar.color,
        }
        cache.set(key, data, timeout)

    @classmethod
    def get_cached_calendar(cls, calendar_id: str) -> dict:
        """Get cached calendar data."""
        key = cls.get_calendar_cache_key(calendar_id)
        return cache.get(key)

    @classmethod
    def invalidate_calendar_cache(cls, calendar_id: str):
        """Invalidate calendar cache."""
        key = cls.get_calendar_cache_key(calendar_id)
        cache.delete(key)

    @classmethod
    def cache_availability(cls, calendar_id: str, booking_type_id: str, slots: list, timeout: int = 300):
        """Cache availability slots."""
        key = cls.get_availability_cache_key(calendar_id, booking_type_id)
        cache.set(key, slots, timeout)

    @classmethod
    def get_cached_availability(cls, calendar_id: str, booking_type_id: str) -> list:
        """Get cached availability slots."""
        key = cls.get_availability_cache_key(calendar_id, booking_type_id)
        return cache.get(key)

    @classmethod
    def invalidate_availability_cache(cls, calendar_id: str):
        """Invalidate all availability cache for a calendar."""
        version_key = cls.get_cache_key(cls.AVAILABILITY_VERSION_PREFIX, calendar_id)
        current_version = cls._get_availability_version(calendar_id)
        cache.set(version_key, current_version + 1)


class QueryOptimizer:
    """Database query optimization utilities."""

    @staticmethod
    def get_calendar_with_permissions(user):
        """Get calendars with optimized permission queries."""
        return Calendar.objects.filter(
            Q(owner=user) |
            Q(visibility='public', tenant=user.tenant) |
            Q(visibility='team', tenant=user.tenant) |
            Q(visibility='shared', allowed_users=user)
        ).select_related('owner', 'tenant').distinct()

    @staticmethod
    def get_events_for_calendars(calendar_ids: list, start_date=None, end_date=None):
        """Get events for multiple calendars with optimized queries."""
        queryset = CalendarEvent.objects.filter(
            calendar_id__in=calendar_ids
        ).select_related('calendar', 'organizer')

        if start_date:
            queryset = queryset.filter(start_time__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(end_time__date__lte=end_date)

        return queryset.order_by('start_time')

    @staticmethod
    def get_availability_with_events(calendar_id: str, start_date, end_date):
        """Get availability slots with related events in single query."""
        availability = AvailabilitySlot.objects.filter(
            calendar_id=calendar_id,
            is_active=True
        ).order_by('day_of_week', 'start_time')

        # Get events in the same date range
        events = CalendarEvent.objects.filter(
            calendar_id=calendar_id,
            start_time__date__gte=start_date,
            end_time__date__lte=end_date
        ).only('start_time', 'end_time')

        return availability, events

    @staticmethod
    def bulk_create_events(events_data: list):
        """Bulk create events for better performance."""
        events = []
        for data in events_data:
            event = CalendarEvent(**data)
            events.append(event)

        CalendarEvent.objects.bulk_create(events)
        return events

    @staticmethod
    def prefetch_calendar_data(calendars):
        """Prefetch related data for calendars."""
        return calendars.prefetch_related(
            'owner',
            'tenant',
            'allowed_users',
            Prefetch(
                'events',
                queryset=CalendarEvent.objects.select_related('organizer').order_by('-start_time')[:10]
            ),
            Prefetch(
                'availability_slots',
                queryset=AvailabilitySlot.objects.filter(is_active=True)
            )
        )


class PerformanceMiddleware:
    """Middleware for performance monitoring and optimization."""

    @staticmethod
    def log_slow_queries(min_duration: float = 1.0):
        """Log slow database queries."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = timezone.now()
                result = func(*args, **kwargs)
                duration = (timezone.now() - start_time).total_seconds()

                if duration > min_duration:
                    logger.warning(
                        f"Slow query in {func.__name__}: {duration:.2f}s, "
                        f"Query count: {len(connection.queries)}"
                    )

                return result
            return wrapper
        return decorator

    @staticmethod
    def cache_result(timeout: int = 300):
        """Cache function results."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                key_data = [func.__name__] + [str(arg) for arg in args[1:]]  # Skip 'self'
                key_data.extend([f"{k}:{v}" for k, v in kwargs.items()])
                cache_key = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

                # Check cache
                cached_result = cache.get(cache_key)
                if cached_result is not None:
                    return cached_result

                # Execute function
                result = func(*args, **kwargs)

                # Cache result
                cache.set(cache_key, result, timeout)
                return result

            return wrapper
        return decorator


class BackgroundTasks:
    """Background task utilities for heavy operations."""

    @staticmethod
    def schedule_availability_calculation(calendar_id: str, booking_type_id: str = None):
        """Schedule background calculation of availability."""
        # This would integrate with your task queue (Celery, RQ, etc.)
        # For now, just log the intent
        logger.info(f"Scheduling availability calculation for calendar {calendar_id}")

        # Example Celery task call:
        # from .tasks import calculate_availability
        # calculate_availability.delay(calendar_id, booking_type_id)

    @staticmethod
    def schedule_bulk_email_notifications(event_ids: list, notification_type: str):
        """Schedule bulk email notifications."""
        logger.info(f"Scheduling {notification_type} notifications for {len(event_ids)} events")

        # Example Celery task call:
        # from .tasks import send_bulk_notifications
        # send_bulk_notifications.delay(event_ids, notification_type)

    @staticmethod
    def schedule_calendar_sync(calendar_ids: list, provider: str):
        """Schedule calendar synchronization with external providers."""
        logger.info(f"Scheduling calendar sync for {len(calendar_ids)} calendars with {provider}")

        # Example Celery task call:
        # from .tasks import sync_calendars
        # sync_calendars.delay(calendar_ids, provider)


# Database optimization utilities
class DatabaseOptimizer:
    """Database performance optimization utilities."""

    @staticmethod
    def analyze_query_performance():
        """Analyze recent query performance."""
        queries = connection.queries[-10:]  # Last 10 queries
        total_time = sum(float(q.get('time', 0)) for q in queries)

        if total_time > 1.0:  # More than 1 second total
            logger.warning(f"High query time: {total_time:.2f}s for {len(queries)} queries")

            # Log slow queries
            for query in queries:
                if float(query.get('time', 0)) > 0.1:  # More than 100ms
                    logger.warning(f"Slow query: {query.get('sql', '')[:200]}...")

    @staticmethod
    def optimize_calendar_queries():
        """Add database-specific optimizations for calendar queries."""
        # This would include things like:
        # - Creating covering indexes
        # - Optimizing table structure
        # - Adding database-specific hints

        with connection.cursor() as cursor:
            # Example PostgreSQL optimizations
            if connection.vendor == 'postgresql':
                # Analyze table statistics
                cursor.execute("ANALYZE moio_calendar_calendarevent;")
                cursor.execute("ANALYZE moio_calendar_calendar;")

                # Create partial indexes for active records
                cursor.execute("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_active_events
                    ON moio_calendar_calendarevent (calendar_id, start_time, end_time)
                    WHERE status != 'cancelled';
                """)

    @staticmethod
    def get_connection_pool_stats():
        """Get database connection pool statistics."""
        return {
            'connections': len(connection.queries),
            'total_queries': len(connection.queries),
            'slow_queries': len([q for q in connection.queries if float(q.get('time', 0)) > 0.1])
        }


# Performance monitoring decorators
def monitor_performance(operation_name: str):
    """Decorator to monitor function performance."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = timezone.now()

            try:
                result = func(*args, **kwargs)
                duration = (timezone.now() - start_time).total_seconds()

                # Log performance metrics
                logger.info(
                    f"Performance: {operation_name} completed in {duration:.3f}s"
                )

                # You could send this to monitoring systems like DataDog, New Relic, etc.
                # Example:
                # metrics_client.histogram(f'calendar.{operation_name}', duration)

                return result

            except Exception as e:
                duration = (timezone.now() - start_time).total_seconds()
                logger.error(
                    f"Performance: {operation_name} failed after {duration:.3f}s: {e}"
                )
                raise

        return wrapper
    return decorator


# Example usage decorators for views
def cache_view(timeout: int = 300):
    """Cache view responses."""
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Create cache key from request
            cache_key = f"view:{request.path}:{hash(str(request.GET))}"

            cached_response = cache.get(cache_key)
            if cached_response and request.method == 'GET':
                return cached_response

            response = func(request, *args, **kwargs)

            if hasattr(response, 'status_code') and response.status_code == 200:
                cache.set(cache_key, response, timeout)

            return response

        return wrapper
    return decorator