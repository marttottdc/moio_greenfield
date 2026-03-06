# Calendar API Reference

## Overview

The Calendar API provides comprehensive calendar management functionality including personal calendars, shared team calendars, events, availability management, resource booking, and public booking capabilities.

## Authentication

All API endpoints (except public booking) require authentication. Use the main platform authentication:

```
Authorization: Bearer <your-token>
```

## Base URL

```
https://your-domain.com/calendar/api/
```

## Core Resources

### Calendars

Manage personal and shared calendars.

#### List Calendars
```http
GET /api/calendars/
```

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "My Calendar",
    "description": "Personal calendar",
    "visibility": "private",
    "color": "#3788d8",
    "is_default": true,
    "owner": 123,
    "allowed_users": [],
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

#### Create Calendar
```http
POST /api/calendars/
Content-Type: application/json

{
  "name": "Team Calendar",
  "description": "Shared team calendar",
  "visibility": "team",
  "color": "#28a745"
}
```

#### Share Calendar
```http
POST /api/calendars/{calendar_id}/share/
Content-Type: application/json

{
  "user_ids": [456, 789],
  "can_edit": true
}
```

### Events

Manage calendar events with conflict prevention.

#### List Events
```http
GET /api/events/?calendar=uuid&start_date=2024-01-01&end_date=2024-01-31
```

**Query Parameters:**
- `calendar`: Filter by calendar ID
- `start_date`: Filter events from this date
- `end_date`: Filter events until this date
- `event_type`: Filter by event type (meeting, appointment, etc.)
- `status`: Filter by status (scheduled, confirmed, etc.)

#### Create Event
```http
POST /api/events/
Content-Type: application/json

{
  "calendar": "uuid",
  "title": "Team Meeting",
  "description": "Weekly team sync",
  "start_time": "2024-01-15T10:00:00Z",
  "end_time": "2024-01-15T11:00:00Z",
  "event_type": "meeting",
  "location": "Conference Room A",
  "meeting_link": "https://meet.google.com/abc-defg-hij"
}
```

#### Update Event
```http
PATCH /api/events/{event_id}/
Content-Type: application/json

{
  "title": "Updated Meeting Title",
  "status": "confirmed"
}
```

#### Add Attendee
```http
POST /api/events/{event_id}/add_attendee/
Content-Type: application/json

{
  "user_id": 456
}
```

### Availability

Manage user availability for bookings.

#### List Availability Slots
```http
GET /api/availability/?calendar=uuid
```

#### Create Availability Slot
```http
POST /api/availability/
Content-Type: application/json

{
  "calendar": "uuid",
  "day_of_week": 0,
  "start_time": "09:00:00",
  "end_time": "17:00:00",
  "slot_duration": "00:30:00"
}
```

### Resources

Manage shared resources like meeting rooms.

#### List Resources
```http
GET /api/resources/?calendar=uuid
```

#### Create Resource
```http
POST /api/resources/
Content-Type: application/json

{
  "calendar": "uuid",
  "name": "Conference Room A",
  "description": "Main conference room",
  "resource_type": "room",
  "capacity": 10,
  "location": "Floor 5"
}
```

#### Book Resource
```http
POST /api/resource-bookings/
Content-Type: application/json

{
  "calendar": "uuid",
  "resource": "uuid",
  "event": "uuid",
  "start_time": "2024-01-15T10:00:00Z",
  "end_time": "2024-01-15T11:00:00Z"
}
```

### Booking Types

Manage Calendly-style booking types.

#### List Booking Types
```http
GET /api/booking-types/?calendar=uuid
```

#### Create Booking Type
```http
POST /api/booking-types/
Content-Type: application/json

{
  "calendar": "uuid",
  "name": "30-minute consultation",
  "description": "Standard consultation session",
  "duration": "00:30:00",
  "booking_slug": "consultation-30min",
  "buffer_time_before": "00:15:00",
  "buffer_time_after": "00:15:00",
  "advance_booking_days": 30
}
```

#### Get Public Booking URL
```http
GET /api/booking-types/{booking_type_id}/public_url/
```

**Response:**
```json
{
  "public_url": "https://your-domain.com/calendar/api/public/availability/consultation-30min/",
  "booking_slug": "consultation-30min"
}
```

## Public Booking API

Endpoints for external users to book appointments without authentication.

### Get Available Booking Types
```http
GET /api/public/booking-types/
```

### Get Available Time Slots
```http
GET /api/public/availability/{booking_slug}/
```

**Response:**
```json
{
  "available_slots": [
    {
      "datetime": "2024-01-15T10:00:00Z",
      "date": "2024-01-15",
      "start_time": "10:00",
      "end_time": "10:30",
      "display_date": "Monday, January 15, 2024",
      "display_time": "10:00 AM"
    }
  ]
}
```

### Create Booking
```http
POST /api/public/book/
Content-Type: application/json

{
  "booking_slug": "consultation-30min",
  "selected_datetime": "2024-01-15T10:00:00Z",
  "external_name": "John Doe",
  "external_email": "john@example.com",
  "external_phone": "+1-555-0123"
}
```

**Success Response:**
```json
{
  "event_id": "uuid",
  "message": "Booking confirmed",
  "event_details": {
    "title": "Booking: 30-minute consultation",
    "start_time": "2024-01-15T10:00:00Z",
    "end_time": "2024-01-15T10:30:00Z",
    "location": "",
    "meeting_link": ""
  }
}
```

## Error Responses

All API endpoints return standardized error responses:

```json
{
  "detail": "Authentication credentials were not provided.",
  "error_code": "authentication_required"
}
```

### Common Error Codes

- `authentication_required`: Missing or invalid authentication
- `permission_denied`: User lacks permission for operation
- `not_found`: Resource not found
- `validation_error`: Invalid request data
- `conflict`: Resource conflict (double-booking, etc.)
- `rate_limited`: Too many requests

## Rate Limiting

API endpoints are rate limited to prevent abuse:

- **Calendar operations**: 200 requests/minute
- **Event operations**: 200 requests/minute
- **Public booking**: 20 requests/minute
- **Strict operations** (sharing, etc.): 10 requests/minute

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 199
X-RateLimit-Reset: 1640995200
```

## Webhooks

The calendar system supports webhooks for real-time notifications:

### Event Webhooks

Configure webhooks to receive notifications when:
- Events are created, updated, or deleted
- Attendees are added or respond to invitations
- Bookings are created or cancelled

### Webhook Payload Example

```json
{
  "event_type": "calendar.event.created",
  "timestamp": "2024-01-15T10:00:00Z",
  "data": {
    "event_id": "uuid",
    "calendar_id": "uuid",
    "title": "Team Meeting",
    "start_time": "2024-01-15T10:00:00Z",
    "end_time": "2024-01-15T11:00:00Z",
    "organizer_id": 123
  }
}
```

## Monitoring & Health Checks

### Health Check
```http
GET /calendar/health/
```

### Metrics
```http
GET /calendar/metrics/
```

Returns Prometheus-compatible metrics for monitoring.