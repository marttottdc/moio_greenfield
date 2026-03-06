---
title: "Moio Calendar API"
slug: "moio-calendar-api"
category: "integrations"
order: 2
status: "published"
summary: "Base path: `/calendar/` (under i18n patterns)"
tags: ["moio_calendar"]
---

## Overview

Base path: `/calendar/` (under i18n patterns)

# moio_calendar - Interfaces

## Public Endpoints

Base path: `/calendar/` (under i18n patterns)

HTML views for calendar interface.

## Events Emitted

None explicitly visible in code.

## Events Consumed

None explicitly visible in code.

## Input/Output Schemas

### Event Status

```
scheduled - Scheduled
confirmed - Confirmed
cancelled - Cancelled
completed - Completed
```

### Event Type

```
meeting - Meeting
appointment - Appointment
call - Call
consultation - Consultation
other - Other
```

### Attendee Status

```
pending - Pending
accepted - Accepted
declined - Declined
maybe - Maybe
```

### Resource Types

```
room - Meeting Room
equipment - Equipment
vehicle - Vehicle
other - Other
```

### Booking Status

```
pending - Pending
confirmed - Confirmed
cancelled - Cancelled
```
