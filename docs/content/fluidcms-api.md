---
title: "Fluidcms API"
slug: "fluidcms-api"
category: "integrations"
order: 2
status: "published"
summary: "Base path: `/api/v1/fluidcms/`"
tags: ["fluidcms"]
---

## Overview

Base path: `/api/v1/fluidcms/`

# fluidcms - Interfaces

## Public Endpoints

Base path: `/api/v1/fluidcms/`

## Events Emitted

None explicitly visible in code.

## Events Consumed

None explicitly visible in code.

## Input/Output Schemas

### Page Status

```
draft - Draft
live - Live
public - Public
archive - Archive
private - Private
```

### Block Types

```
header - Header
hero - Hero
rich_text - Rich Text
feature_list - Feature List
heading_content - Heading Content
featured - Featured
cta - Call To Action
blog - Blog
news - News
services - Services
topic_content - Topic Content
kpi - KPI
articles - Articles
faq - FAQ
testimonials - Testimonials
brands - Brands/Logos
contact_info - Contact Info
quote - Quote
footer - Footer
custom - Custom
```

### Media Types

```
image - Image
video - Video
document - Document
other - Other
```

### Article Status

```
draft - Draft
published - Published
archived - Archived
```

### Bundle Version Status

```
draft - Draft
submitted - Submitted for Review
published - Published
deprecated - Deprecated
```

### CTA Action Types

```
none - No action
external_link - Opens URL in new tab
internal_link - Router navigation
scroll_to_anchor - Smooth scroll
topic_chat - Opens chat modal for topic
article_chat - Opens chat modal for article
simple_modal - Opens modal with content
legal_document - Opens legal doc modal
reveal_content - Toggles visibility
collapse_content - Toggles collapse state
```
