---
title: "Moio Calendar Overview"
slug: "moio-calendar-overview"
category: "integrations"
order: 1
status: "published"
summary: "Calendar and scheduling system with event management, availability slots, resource booking, and public booking links."
tags: ["moio_calendar"]
---

## Overview

Calendar and scheduling system with event management, availability slots, resource booking, and public booking links.

# moio_calendar

## Responsibility

Calendar and scheduling system with event management, availability slots, resource booking, and public booking links.

## What it Owns

- **CalendarEvent**: Events with title, time, type, status, attendees
- **EventAttendee**: Event attendance tracking (pending, accepted, declined)
- **AvailabilitySlot**: User availability definitions (day/time slots)
- **SharedResource**: Bookable resources (rooms, equipment, vehicles)
- **ResourceBooking**: Resource reservations linked to events
- **BookingType**: Predefined booking types (like Calendly event types)

## Core Components

### Event Management
- Event types: meeting, appointment, call, consultation, other
- Event statuses: scheduled, confirmed, cancelled, completed
- Internal and external attendees
- Meeting links and location

### Availability System
- Weekly availability slots per user
- Configurable slot duration
- Day of week configuration

### Resource Booking
- Shared resource definitions
- Capacity tracking
- Advance booking limits
- Min/max booking duration

### Public Booking (Calendly-like)
- BookingType definitions with duration
- Public booking slugs
- Buffer time before/after
- Advance booking limits

## Event Status Flow

```
SCHEDULED
  │
  ├── User confirms
  │
  ▼
CONFIRMED
  │
  ├── Event occurs
  │
  ▼
COMPLETED

OR

SCHEDULED/CONFIRMED
  │
  ├── User cancels
  │
  ▼
CANCELLED
```

## Attendee Response Flow

```
PENDING
  │
  ├── ACCEPTED
  ├── DECLINED
  └── MAYBE
```

## What it Does NOT Do

- Does not integrate with external calendars directly (see portal integrations)
- Does not send notifications (delegates to chatbot/campaigns)
- Does not handle authentication (delegates to portal)
