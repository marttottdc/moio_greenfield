---
title: "Moio Calendar Lifecycle"
slug: "moio-calendar-lifecycle"
category: "integrations"
order: 3
status: "published"
summary: "No explicit startup behavior defined."
tags: ["moio_calendar"]
---

## Overview

No explicit startup behavior defined.

# moio_calendar - Lifecycle

## Startup Behavior

No explicit startup behavior defined.

## Runtime Behavior

### Event Creation

- Events created with organizer as the creating user
- External attendees can be specified without User accounts
- Events can be marked public for external booking

### Availability Management

- AvailabilitySlot defines recurring weekly availability
- slot_duration determines granularity of bookable slots

### Resource Booking

- ResourceBooking links events to shared resources
- Booking constraints: advance_booking_days, min/max duration

## Shutdown Behavior

No explicit shutdown behavior defined.
