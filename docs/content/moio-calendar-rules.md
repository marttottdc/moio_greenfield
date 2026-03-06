---
title: "Moio Calendar Rules & Constraints"
slug: "moio-calendar-rules"
category: "integrations"
order: 5
status: "published"
summary: "- CalendarEvent.booking_link unique globally - EventAttendee (event, user) unique - AvailabilitySlot (user, day_of_week, start_time, end_time) unique - BookingType.booking_slug unique globally"
tags: ["moio_calendar"]
---

## Overview

- CalendarEvent.booking_link unique globally - EventAttendee (event, user) unique - AvailabilitySlot (user, day_of_week, start_time, end_time) unique - BookingType.booking_slug unique globally

# moio_calendar - Invariants

## Enforced Rules

- CalendarEvent.booking_link unique globally
- EventAttendee (event, user) unique
- AvailabilitySlot (user, day_of_week, start_time, end_time) unique
- BookingType.booking_slug unique globally
