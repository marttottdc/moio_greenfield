"""
Security configuration and utilities for the calendar app.
Includes rate limiting, CORS, input validation, and security middleware.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone
from django.conf import settings
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import Throttled
import logging
import re

logger = logging.getLogger(__name__)


class CalendarPermission(BasePermission):
    """
    Custom permission class for calendar operations.
    Checks calendar-specific permissions based on visibility and sharing.
    """

    def has_object_permission(self, request, view, obj):
        """Check permissions for specific calendar objects."""

        # For calendar objects
        if hasattr(obj, 'can_view'):
            if request.method in ['GET', 'HEAD', 'OPTIONS']:
                return obj.can_view(request.user)
            else:  # POST, PUT, DELETE
                return obj.can_edit(request.user)

        # For events
        if hasattr(obj, 'calendar'):
            calendar = obj.calendar
            if request.method in ['GET', 'HEAD', 'OPTIONS']:
                return calendar.can_view(request.user)
            else:  # POST, PUT, DELETE
                return calendar.can_edit(request.user)

        # For other objects with calendar relation
        if hasattr(obj, 'calendar_id'):
            try:
                from .models import Calendar
                calendar = Calendar.objects.get(id=obj.calendar_id)
                if request.method in ['GET', 'HEAD', 'OPTIONS']:
                    return calendar.can_view(request.user)
                else:
                    return calendar.can_edit(request.user)
            except Calendar.DoesNotExist:
                return False

        return False


class StrictCalendarThrottle(UserRateThrottle):
    """Stricter rate limiting for sensitive calendar operations."""

    scope = 'calendar_strict'
    rate = '10/minute'  # 10 requests per minute for sensitive ops


class CalendarThrottle(UserRateThrottle):
    """Standard rate limiting for calendar operations."""

    scope = 'calendar'
    rate = '100/minute'  # 100 requests per minute


class PublicBookingThrottle(AnonRateThrottle):
    """Rate limiting for public booking endpoints."""

    scope = 'public_booking'
    rate = '20/minute'  # 20 requests per minute for public bookings


class InputSanitizer:
    """Utility class for sanitizing user inputs."""

    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """Sanitize string inputs."""
        if not isinstance(value, str):
            return ""

        # Remove null bytes and control characters
        value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)

        # Trim whitespace
        value = value.strip()

        # Truncate if too long
        if len(value) > max_length:
            value = value[:max_length]

        return value

    @staticmethod
    def validate_email(email: str) -> bool:
        """Basic email validation."""
        email_pattern = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
        return bool(email_pattern.match(email.strip()))

    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Basic phone number validation."""
        # Allow various phone formats
        phone = re.sub(r'[^\d+\-\s\(\)]', '', phone)
        return 7 <= len(re.sub(r'[^\d]', '', phone)) <= 15


class SecurityMiddleware:
    """Security middleware for calendar operations."""

    @staticmethod
    def check_request_sanity(request):
        """Perform basic sanity checks on requests."""
        # Check for suspicious patterns in headers
        suspicious_headers = [
            'X-Forwarded-For', 'X-Real-IP', 'X-Client-IP'
        ]

        for header in suspicious_headers:
            if header in request.META and len(request.META[header]) > 100:
                logger.warning(f"Suspicious header detected: {header}")
                raise PermissionDenied("Invalid request")

        # Check for extremely long query parameters
        for key, value in request.GET.items():
            if len(str(value)) > 1000:
                logger.warning(f"Query parameter too long: {key}")
                raise PermissionDenied("Invalid request")

        # Check for SQL injection patterns (basic)
        sql_patterns = [
            r';\s*(select|insert|update|delete|drop|create|alter)',
            r'union\s+select',
            r'--',
            r'/\*.*\*/'
        ]

        for key, value in {**request.GET.dict(), **request.POST.dict()}.items():
            value_str = str(value).lower()
            for pattern in sql_patterns:
                if re.search(pattern, value_str, re.IGNORECASE):
                    logger.warning(f"SQL injection pattern detected in {key}")
                    raise PermissionDenied("Invalid request")

    @staticmethod
    def log_security_event(event_type: str, user, details: dict = None):
        """Log security-related events."""
        log_data = {
            'event_type': event_type,
            'user_id': str(user.id) if user and user.is_authenticated else None,
            'user_email': user.email if user and user.is_authenticated else None,
            'timestamp': timezone.now().isoformat(),
            'details': details or {}
        }

        logger.warning(f"SECURITY_EVENT: {log_data}")


def require_calendar_permission(calendar, permission_type='view'):
    """
    Decorator to require specific calendar permissions.

    Args:
        calendar: Calendar instance or callable that returns calendar
        permission_type: 'view' or 'edit'
    """
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            # Get calendar instance
            if callable(calendar):
                cal = calendar(request, *args, **kwargs)
            else:
                cal = calendar

            if not cal:
                raise Http404("Calendar not found")

            if permission_type == 'view' and not cal.can_view(request.user):
                SecurityMiddleware.log_security_event(
                    'calendar_access_denied',
                    request.user,
                    {'calendar_id': str(cal.id), 'permission_type': 'view'}
                )
                raise PermissionDenied("You don't have permission to view this calendar")

            if permission_type == 'edit' and not cal.can_edit(request.user):
                SecurityMiddleware.log_security_event(
                    'calendar_access_denied',
                    request.user,
                    {'calendar_id': str(cal.id), 'permission_type': 'edit'}
                )
                raise PermissionDenied("You don't have permission to edit this calendar")

            return func(request, *args, **kwargs)
        return wrapper
    return decorator


def rate_limit_by_user(scope: str, rates: dict = None):
    """
    Dynamic rate limiting based on user type.

    Args:
        scope: Throttle scope name
        rates: Dict of user_type -> rate (e.g., {'premium': '1000/minute'})
    """
    class DynamicRateThrottle(UserRateThrottle):
        def __init__(self):
            super().__init__()
            self.scope = scope

        def get_rate(self):
            if rates and hasattr(self, 'get_identified_user'):
                user = self.get_identified_user()
                if user and hasattr(user, 'user_type'):
                    return rates.get(user.user_type, self.rate)
            return getattr(self, 'default_rate', '100/minute')

    return DynamicRateThrottle


# CORS configuration for calendar app
CALENDAR_CORS_ALLOWED_ORIGINS = getattr(settings, 'CALENDAR_CORS_ALLOWED_ORIGINS', [
    'http://localhost:3000',  # React dev server
    'http://localhost:8000',  # Django dev server
])

CALENDAR_CORS_ALLOWED_METHODS = [
    'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'
]

CALENDAR_CORS_ALLOWED_HEADERS = [
    'authorization',
    'content-type',
    'x-csrftoken',
    'x-requested-with',
]

# API Key authentication for integrations
CALENDAR_API_KEY_HEADER = 'X-Calendar-API-Key'