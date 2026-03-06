"""
Monitoring, logging, and error tracking for the calendar app.
"""

import time
import logging
import json
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.db import connection
from django.core.exceptions import ValidationError
import uuid

logger = logging.getLogger(__name__)


class CalendarMonitor:
    """Monitoring utilities for calendar operations."""

    @staticmethod
    def get_request_id():
        """Generate or get request correlation ID."""
        return str(uuid.uuid4())

    @staticmethod
    def log_operation(operation: str, duration: float, success: bool, **kwargs):
        """Log operation metrics."""
        log_data = {
            'operation': operation,
            'duration': duration,
            'success': success,
            'timestamp': timezone.now().isoformat(),
            **kwargs
        }

        if success:
            logger.info(f"OPERATION_SUCCESS: {json.dumps(log_data)}")
        else:
            logger.error(f"OPERATION_FAILED: {json.dumps(log_data)}")

    @staticmethod
    def log_business_event(event_type: str, **kwargs):
        """Log business events for analytics."""
        event_data = {
            'event_type': event_type,
            'timestamp': timezone.now().isoformat(),
            **kwargs
        }

        logger.info(f"BUSINESS_EVENT: {json.dumps(event_data)}")

    @staticmethod
    def log_security_event(event_type: str, user, **kwargs):
        """Log security-related events."""
        event_data = {
            'event_type': event_type,
            'timestamp': timezone.now().isoformat(),
            'user_id': str(user.id) if user and hasattr(user, 'id') else None,
            'user_email': getattr(user, 'email', None) if user else None,
            **kwargs
        }

        logger.warning(f"SECURITY_EVENT: {json.dumps(event_data)}")

    @staticmethod
    def record_metric(metric_name: str, value: float, tags: dict = None):
        """Record custom metrics."""
        metric_data = {
            'metric': metric_name,
            'value': value,
            'timestamp': timezone.now().isoformat(),
            'tags': tags or {}
        }

        logger.info(f"METRIC: {json.dumps(metric_data)}")

        # Send to monitoring service (DataDog, New Relic, etc.)
        # Example:
        # if hasattr(settings, 'DATADOG_API_KEY'):
        #     datadog_client.increment(metric_name, value, tags=tags)


class ErrorTracker:
    """Error tracking and reporting utilities."""

    @staticmethod
    def capture_exception(exc: Exception, **context):
        """Capture and report exceptions."""
        error_data = {
            'error_type': type(exc).__name__,
            'error_message': str(exc),
            'timestamp': timezone.now().isoformat(),
            **context
        }

        logger.error(f"EXCEPTION: {json.dumps(error_data)}", exc_info=True)

        # Send to error tracking service (Sentry, Rollbar, etc.)
        # Example Sentry integration:
        # if hasattr(settings, 'SENTRY_DSN'):
        #     from sentry_sdk import capture_exception
        #     capture_exception(exc)

    @staticmethod
    def capture_validation_error(error: ValidationError, **context):
        """Capture validation errors."""
        error_data = {
            'error_type': 'ValidationError',
            'error_messages': error.messages,
            'timestamp': timezone.now().isoformat(),
            **context
        }

        logger.warning(f"VALIDATION_ERROR: {json.dumps(error_data)}")

    @staticmethod
    def track_api_error(status_code: int, endpoint: str, **context):
        """Track API errors by status code."""
        error_data = {
            'status_code': status_code,
            'endpoint': endpoint,
            'timestamp': timezone.now().isoformat(),
            **context
        }

        if status_code >= 500:
            logger.error(f"API_ERROR_5XX: {json.dumps(error_data)}")
        elif status_code >= 400:
            logger.warning(f"API_ERROR_4XX: {json.dumps(error_data)}")


class PerformanceTracker:
    """Performance monitoring utilities."""

    @staticmethod
    def track_query_performance():
        """Track database query performance."""
        queries = connection.queries[-10:]  # Last 10 queries
        total_time = sum(float(q.get('time', 0)) for q in queries)

        if total_time > 1.0:  # More than 1 second total
            CalendarMonitor.record_metric(
                'calendar.db_query_total_time',
                total_time,
                tags={'query_count': len(queries)}
            )

            # Log slow queries
            for query in queries:
                query_time = float(query.get('time', 0))
                if query_time > 0.1:  # More than 100ms
                    CalendarMonitor.record_metric(
                        'calendar.db_slow_query',
                        query_time,
                        tags={'query_type': 'slow'}
                    )

    @staticmethod
    def track_api_performance(endpoint: str, method: str, duration: float, status_code: int):
        """Track API endpoint performance."""
        CalendarMonitor.record_metric(
            f'calendar.api.{endpoint}',
            duration,
            tags={
                'method': method,
                'status_code': status_code,
                'status_family': f'{status_code // 100}xx'
            }
        )

    @staticmethod
    def track_business_metrics():
        """Track business-related metrics."""
        from django.db.models import Count, Q
        from django.utils import timezone as django_timezone
        from datetime import timedelta

        # Calculate metrics for the last 24 hours
        yesterday = django_timezone.now() - timedelta(days=1)

        # Event creation rate
        from .models import CalendarEvent, Calendar
        events_created = CalendarEvent.objects.filter(
            created_at__gte=yesterday
        ).count()

        CalendarMonitor.record_metric(
            'calendar.events_created_24h',
            events_created
        )

        # Active calendars
        active_calendars = Calendar.objects.filter(
            events__created_at__gte=yesterday
        ).distinct().count()

        CalendarMonitor.record_metric(
            'calendar.active_calendars_24h',
            active_calendars
        )

        # Public booking conversions
        public_events = CalendarEvent.objects.filter(
            created_at__gte=yesterday,
            is_public=True
        ).count()

        CalendarMonitor.record_metric(
            'calendar.public_bookings_24h',
            public_events
        )


def monitor_api_performance(view_name: str = None):
    """Decorator to monitor API view performance."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            request = None
            if args:
                if hasattr(args[0], 'method'):
                    request = args[0]
                elif len(args) > 1 and hasattr(args[1], 'method'):
                    request = args[1]

            if request is None:
                return func(*args, **kwargs)

            start_time = time.time()

            try:
                response = func(*args, **kwargs)
                duration = time.time() - start_time

                # Track performance
                resolver_match = getattr(request, 'resolver_match', None)
                endpoint = view_name or (
                    f"{resolver_match.app_name}.{resolver_match.url_name}"
                    if resolver_match else func.__name__
                )
                PerformanceTracker.track_api_performance(
                    endpoint=endpoint,
                    method=request.method,
                    duration=duration,
                    status_code=getattr(response, 'status_code', 200)
                )

                # Log operation
                CalendarMonitor.log_operation(
                    operation=endpoint,
                    duration=duration,
                    success=True,
                    method=request.method,
                    user_id=str(request.user.id) if getattr(request.user, 'is_authenticated', False) else None
                )

                return response

            except Exception as e:
                duration = time.time() - start_time

                # Track failed operation
                resolver_match = getattr(request, 'resolver_match', None)
                endpoint = view_name or (
                    f"{resolver_match.app_name}.{resolver_match.url_name}"
                    if resolver_match else func.__name__
                )
                PerformanceTracker.track_api_performance(
                    endpoint=endpoint,
                    method=request.method,
                    duration=duration,
                    status_code=500
                )

                # Log error
                CalendarMonitor.log_operation(
                    operation=endpoint,
                    duration=duration,
                    success=False,
                    method=request.method,
                    error=str(e),
                    user_id=str(request.user.id) if getattr(request.user, 'is_authenticated', False) else None
                )

                # Track error
                ErrorTracker.capture_exception(e, endpoint=endpoint, user=request.user)
                raise

        return wrapper
    return decorator


def health_check(request):
    """Calendar app health check endpoint."""
    from .models import Calendar, CalendarEvent

    health_data = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'checks': {}
    }

    try:
        # Database connectivity check
        calendar_count = Calendar.objects.count()
        health_data['checks']['database'] = {
            'status': 'ok',
            'calendar_count': calendar_count
        }

        # Recent activity check
        recent_events = CalendarEvent.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        health_data['checks']['recent_activity'] = {
            'status': 'ok',
            'events_last_hour': recent_events
        }

        # Performance metrics
        health_data['checks']['performance'] = {
            'status': 'ok',
            'db_queries': len(connection.queries),
            'total_query_time': sum(float(q.get('time', 0)) for q in connection.queries)
        }

        status_code = 200

    except Exception as e:
        health_data['status'] = 'unhealthy'
        health_data['error'] = str(e)
        ErrorTracker.capture_exception(e, context='health_check')
        status_code = 503

    return JsonResponse(health_data, status=status_code)


def metrics_endpoint(request):
    """Prometheus-style metrics endpoint."""
    from django.db.models import Count
    from .models import Calendar, CalendarEvent, CalendarEvent

    # Calculate current metrics
    total_calendars = Calendar.objects.count()
    total_events = CalendarEvent.objects.count()
    active_events = CalendarEvent.objects.filter(
        start_time__gte=timezone.now(),
        status__in=['scheduled', 'confirmed']
    ).count()

    # Format as Prometheus metrics
    metrics = f"""# HELP calendar_total_calendars Total number of calendars
# TYPE calendar_total_calendars gauge
calendar_total_calendars {total_calendars}

# HELP calendar_total_events Total number of events
# TYPE calendar_total_events gauge
calendar_total_events {total_events}

# HELP calendar_active_events Number of upcoming active events
# TYPE calendar_active_events gauge
calendar_active_events {active_events}

# HELP calendar_health_check_timestamp Timestamp of last health check
# TYPE calendar_health_check_timestamp gauge
calendar_health_check_timestamp {int(timezone.now().timestamp())}
"""

    return JsonResponse({'metrics': metrics}, status=200)


class CalendarLoggingMiddleware:
    """Middleware for comprehensive calendar logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Add request ID for correlation
        request.request_id = CalendarMonitor.get_request_id()

        # Log request start
        logger.info(f"REQUEST_START: {request.method} {request.path} [ID: {request.request_id}]")

        start_time = time.time()
        response = self.get_response(request)
        duration = time.time() - start_time

        # Log request completion
        logger.info(
            f"REQUEST_COMPLETE: {request.method} {request.path} "
            f"-> {response.status_code} ({duration:.3f}s) [ID: {request.request_id}]"
        )

        # Track API performance for calendar endpoints
        if request.path.startswith('/api/v1/calendar'):
            PerformanceTracker.track_api_performance(
                endpoint=request.path,
                method=request.method,
                duration=duration,
                status_code=response.status_code
            )

        return response

    def process_exception(self, request, exception):
        """Log exceptions with request context."""
        ErrorTracker.capture_exception(
            exception,
            request_id=getattr(request, 'request_id', None),
            path=request.path,
            method=request.method,
            user=getattr(request, 'user', None)
        )


# Periodic task for business metrics (to be called by Celery beat or similar)
def collect_business_metrics():
    """Collect and log business metrics."""
    try:
        PerformanceTracker.track_business_metrics()
        logger.info("Business metrics collected successfully")
    except Exception as e:
        ErrorTracker.capture_exception(e, context='business_metrics_collection')