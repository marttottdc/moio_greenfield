"""
Django settings configuration for the moio_calendar app.
Add this to your main Django settings file.
"""

# Rate limiting configuration
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        # Calendar-specific rates
        'calendar': '200/minute',
        'calendar_strict': '10/minute',
        'public_booking': '20/minute',
    }
}

# CORS configuration for calendar app
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React dev server
    "http://localhost:8000",  # Django dev server
    # Add your production domains here
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_METHODS = [
    'GET',
    'POST',
    'PUT',
    'PATCH',
    'DELETE',
    'OPTIONS',
]

CORS_ALLOWED_HEADERS = [
    'authorization',
    'content-type',
    'x-csrftoken',
    'x-requested-with',
    'x-calendar-api-key',
]

# Calendar-specific settings
CALENDAR_SETTINGS = {
    # Default calendar colors
    'DEFAULT_COLORS': [
        '#3788d8',  # Blue
        '#28a745',  # Green
        '#dc3545',  # Red
        '#ffc107',  # Yellow
        '#6f42c1',  # Purple
        '#e83e8c',  # Pink
        '#20c997',  # Teal
        '#fd7e14',  # Orange
    ],

    # Maximum advance booking days
    'MAX_ADVANCE_BOOKING_DAYS': 365,

    # Default slot duration in minutes
    'DEFAULT_SLOT_DURATION_MINUTES': 30,

    # Business hours (for availability validation)
    'BUSINESS_HOURS': {
        'start': '08:00',
        'end': '18:00',
        'timezone': 'UTC'
    },

    # Email settings
    'EMAIL_TEMPLATES': {
        'booking_confirmation': 'calendar/email/booking_confirmation.html',
        'booking_reminder': 'calendar/email/booking_reminder.html',
        'event_invitation': 'calendar/email/event_invitation.html',
    },

    # Security settings
    'MAX_BOOKING_REQUESTS_PER_HOUR': 50,
    'MAX_AVAILABILITY_SLOTS_PER_USER': 50,
    'MAX_BOOKING_TYPES_PER_CALENDAR': 20,

    # Cache settings
    'AVAILABILITY_CACHE_TIMEOUT': 300,  # 5 minutes
    'CALENDAR_CACHE_TIMEOUT': 600,     # 10 minutes
}

# Logging configuration for calendar security events
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'calendar_security': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': 'logs/calendar_security.log',
            'formatter': 'security',
        },
    },
    'formatters': {
        'security': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'loggers': {
        'moio_calendar.security': {
            'handlers': ['calendar_security'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}