---
title: "Fluidcommerce API"
slug: "fluidcommerce-api"
category: "integrations"
order: 2
status: "published"
summary: "Base path: `/api/v1/fluidcommerce/`"
tags: ["fluidcommerce"]
---

## Overview

Base path: `/api/v1/fluidcommerce/`

# fluidcommerce - Interfaces

## Public Endpoints

Base path: `/api/v1/fluidcommerce/`

## Events Emitted

None explicitly visible in code.

## Events Consumed

None explicitly visible in code.

## Input/Output Schemas

### Product Status

```
draft - Draft
active - Active
archived - Archived
```

### Product Types

```
STD - Standard
VAR - Variable (has variants)
```

### Attribute Types

```
text - Text
number - Number
boolean - Boolean
select - Select
multiselect - Multi-Select
color - Color
```

### Media Types

```
image - Image
video - Video
```

### Order Status

```
pending - Pending
confirmed - Confirmed
processing - Processing
shipped - Shipped
delivered - Delivered
cancelled - Cancelled
refunded - Refunded
```

### Payment Status

```
pending - Pending
paid - Paid
partially_paid - Partially Paid
refunded - Refunded
failed - Failed
```
