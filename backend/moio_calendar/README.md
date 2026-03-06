# Calendar App

A comprehensive SaaS calendar application with multi-calendar support, resource booking, availability management, and public booking capabilities.

## Features

### 🎯 Core Functionality
- **Multi-Calendar Support**: Personal calendars, team calendars, and shared calendars
- **Event Management**: Create, update, and manage calendar events with conflict prevention
- **Resource Booking**: Book meeting rooms, equipment, and other shared resources
- **Availability Management**: Define recurring availability slots for bookings
- **Public Booking**: Allow external users to book appointments without accounts

### 🔐 Security & Permissions
- **Granular Permissions**: Owner, editor, and viewer roles for shared calendars
- **Tenant Isolation**: All data properly scoped by tenant
- **Rate Limiting**: API protection against abuse
- **Input Validation**: Comprehensive validation and sanitization
- **Audit Logging**: Track all calendar operations

### 📊 Advanced Features
- **Conflict Prevention**: Automatic detection and prevention of double-bookings
- **Business Logic Validation**: Enforce business rules and constraints
- **Caching**: Performance optimization with Redis caching
- **Monitoring**: Comprehensive logging and error tracking
- **API-First Design**: Complete REST API for all functionality

## Architecture

### Models
- **Calendar**: Core calendar entity with ownership and sharing
- **CalendarEvent**: Events with conflict detection
- **AvailabilitySlot**: User availability for bookings
- **SharedResource**: Bookable resources (rooms, equipment)
- **ResourceBooking**: Resource reservations
- **BookingType**: Calendly-style event types
- **EventAttendee**: Event participants

### APIs
- **Calendar Management**: CRUD operations for calendars
- **Event Management**: Full event lifecycle with validation
- **Resource Management**: Resource and booking operations
- **Public Booking**: No-auth endpoints for external bookings
- **Availability**: Time slot management and checking

## Quick Start

### 1. Installation

Add to your Django project:

```python
# settings.py
INSTALLED_APPS = [
    # ... other apps
    'moio_calendar',
]

# Calendar-specific settings
CALENDAR_SETTINGS = {
    'DEFAULT_COLORS': ['#3788d8', '#28a745', '#dc3545'],
    'MAX_ADVANCE_BOOKING_DAYS': 365,
    'DEFAULT_SLOT_DURATION_MINUTES': 30,
}

# Rate limiting
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'calendar': '200/minute',
        'calendar_strict': '10/minute',
        'public_booking': '20/minute',
    }
}
```

### 2. Database Migration

```bash
python manage.py makemigrations moio_calendar
python manage.py migrate
```

### 3. URL Configuration

```python
# urls.py
urlpatterns = [
    # ... other patterns
    path('calendar/', include('moio_calendar.urls')),
]
```

## API Usage Examples

### Create a Calendar
```bash
curl -X POST /calendar/api/calendars/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Team Calendar",
    "visibility": "team",
    "color": "#28a745"
  }'
```

### Create an Event
```bash
curl -X POST /calendar/api/events/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "calendar": "calendar-uuid",
    "title": "Team Meeting",
    "start_time": "2024-01-15T10:00:00Z",
    "end_time": "2024-01-15T11:00:00Z",
    "event_type": "meeting"
  }'
```

### Public Booking
```bash
# Get available slots
curl /calendar/api/public/availability/consultation-30min/

# Create booking
curl -X POST /calendar/api/public/book/ \
  -H "Content-Type: application/json" \
  -d '{
    "booking_slug": "consultation-30min",
    "selected_datetime": "2024-01-15T10:00:00Z",
    "external_name": "John Doe",
    "external_email": "john@example.com"
  }'
```

## Configuration Options

### Calendar Settings

```python
CALENDAR_SETTINGS = {
    # Default calendar colors for new calendars
    'DEFAULT_COLORS': ['#3788d8', '#28a745', '#dc3545', '#ffc107'],

    # Maximum days in advance for bookings
    'MAX_ADVANCE_BOOKING_DAYS': 365,

    # Default duration for availability slots
    'DEFAULT_SLOT_DURATION_MINUTES': 30,

    # Business hours
    'BUSINESS_HOURS': {
        'start': '08:00',
        'end': '18:00',
        'timezone': 'UTC'
    },

    # Email templates
    'EMAIL_TEMPLATES': {
        'booking_confirmation': 'calendar/email/booking_confirmation.html',
        'event_invitation': 'calendar/email/event_invitation.html',
    },

    # Resource constraints
    'MAX_BOOKING_TYPES_PER_CALENDAR': 20,
    'MAX_AVAILABILITY_SLOTS_PER_USER': 50,
}
```

### Security Settings

```python
# Rate limiting
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'calendar': '200/minute',
        'calendar_strict': '10/minute',
        'public_booking': '20/minute',
    }
}

# CORS settings
CORS_ALLOWED_ORIGINS = [
    'https://your-frontend-domain.com',
    'http://localhost:3000',  # Development
]

# Logging
LOGGING = {
    'loggers': {
        'moio_calendar.security': {
            'level': 'WARNING',
            'handlers': ['security_file'],
        },
        'moio_calendar.monitoring': {
            'level': 'INFO',
            'handlers': ['calendar_file'],
        }
    }
}
```

## Development

### Running Tests

```bash
# Unit tests
python manage.py test moio_calendar.tests.CalendarModelTest

# API tests
python manage.py test moio_calendar.tests.CalendarAPITestCase

# All tests
python manage.py test moio_calendar
```

### Code Quality

```bash
# Linting
flake8 moio_calendar/

# Type checking
mypy moio_calendar/

# Test coverage
coverage run --source=moio_calendar manage.py test
coverage report
```

## Monitoring & Health Checks

### Health Check Endpoint
```
GET /calendar/health/
```

Returns system health status and metrics.

### Metrics Endpoint
```
GET /calendar/metrics/
```

Provides Prometheus-compatible metrics.

### Log Files
- Security events: `logs/calendar_security.log`
- Application logs: `logs/calendar.log`
- Performance metrics: `logs/calendar_performance.log`

## Integration Examples

### Frontend Integration
```javascript
// Load user calendars
const calendars = await fetch('/calendar/api/calendars/', {
  headers: { 'Authorization': `Bearer ${token}` }
});

// Create event
const event = await fetch('/calendar/api/events/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    calendar: calendarId,
    title: 'New Event',
    start_time: '2024-01-15T10:00:00Z',
    end_time: '2024-01-15T11:00:00Z'
  })
});
```

### External Calendar Sync
```python
from moio_calendar.integrations import GoogleCalendarSync

sync = GoogleCalendarSync(user_token)
sync.sync_events(calendar_id)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

### Development Guidelines

- **API First**: All features must have complete API coverage
- **Security First**: Implement proper authentication and authorization
- **Test Coverage**: Maintain >90% test coverage
- **Documentation**: Update docs for all new features
- **Performance**: Optimize database queries and implement caching

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Documentation: [API Reference](docs/API_REFERENCE.md)
- Integration Guides: [Integration Guides](docs/INTEGRATION_GUIDES.md)
- Issues: GitHub Issues
- Email: support@yourcompany.com