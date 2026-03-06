---
title: "Moio Calendar Data Model"
slug: "moio-calendar-data"
category: "integrations"
order: 4
status: "published"
summary: "- id: UUID (PK) - title: CharField - description: TextField - start_time, end_time: DateTimeField - event_type: CharField - status: CharField - organizer: FK → User - attendees: M2M → User (through Ev"
tags: ["moio_calendar"]
---

## Overview

- id: UUID (PK) - title: CharField - description: TextField - start_time, end_time: DateTimeField - event_type: CharField - status: CharField - organizer: FK → User - attendees: M2M → User (through Ev

# moio_calendar - Data

## Owned Data Models

### CalendarEvent

- id: UUID (PK)
- title: CharField
- description: TextField
- start_time, end_time: DateTimeField
- event_type: CharField
- status: CharField
- organizer: FK → User
- attendees: M2M → User (through EventAttendee)
- external_attendee_name: CharField
- external_attendee_email: EmailField
- external_attendee_phone: CharField
- location: CharField
- meeting_link: URLField
- is_public: BooleanField
- booking_link: CharField (unique)
- tenant: FK → Tenant

### EventAttendee

- event: FK → CalendarEvent
- user: FK → User
- status: CharField
- added_at: DateTimeField

Constraint: unique (event, user)

### AvailabilitySlot

- id: UUID (PK)
- user: FK → User
- day_of_week: IntegerField (0-6, Monday-Sunday)
- start_time, end_time: TimeField
- slot_duration: DurationField
- is_active: BooleanField
- tenant: FK → Tenant

Constraint: unique (user, day_of_week, start_time, end_time)

### SharedResource

- id: UUID (PK)
- name: CharField
- description: TextField
- resource_type: CharField
- capacity: IntegerField
- location: CharField
- advance_booking_days: IntegerField
- min_booking_duration, max_booking_duration: DurationField
- is_active: BooleanField
- tenant: FK → Tenant

### ResourceBooking

- id: UUID (PK)
- resource: FK → SharedResource
- event: FK → CalendarEvent
- start_time, end_time: DateTimeField
- booked_by: FK → User
- status: CharField
- tenant: FK → Tenant

### BookingType

- id: UUID (PK)
- name: CharField
- description: TextField
- duration: DurationField
- buffer_time_before, buffer_time_after: DurationField
- advance_booking_days: IntegerField
- organizer: FK → User
- booking_slug: SlugField (unique)
- is_active: BooleanField
- tenant: FK → Tenant

## External Data Read

- portal.Tenant
- portal.MoioUser

## External Data Written

None directly.
