---
title: "Fluidcms Lifecycle"
slug: "fluidcms-lifecycle"
category: "integrations"
order: 3
status: "published"
summary: "No explicit startup behavior defined."
tags: ["fluidcms"]
---

## Overview

No explicit startup behavior defined.

# fluidcms - Lifecycle

## Startup Behavior

No explicit startup behavior defined.

## Runtime Behavior

### Page Management

- FluidPage.clean() ensures only one home page per tenant
- FluidBlock.save() auto-sets tenant from page if not set
- FluidBlock.clean() validates tenant consistency with page

### Bundle Version FSM

```
draft → submitted (submit)
  - Materializes BlockDefinitions from manifest

submitted → draft (reject)
submitted → published (publish)
  - Requires validation to pass
  - Re-materializes BlockDefinitions

published → deprecated (deprecate)
```

### Block Definition Materialization

BlockBundleVersion.materialize_block_definitions() creates BlockDefinition instances from manifest JSON.

### Bundle Installation

- BundleInstall.clean() ensures only one active installation per bundle per tenant
- Only published bundle versions can be installed

### Page Versioning

- PageVersion.save() auto-increments version_number per page
- version_number is sequential per page

### Article Publishing

- Article.publish() sets status and published_at
- Article.archive() sets status to archived
- calculate_reading_time() estimates based on word count (200 wpm)

### Session Engagement

- VisitorSession.touch() updates last_engaged_at
- Conversation.touch() updates last_message_at

## Shutdown Behavior

No explicit shutdown behavior defined.
