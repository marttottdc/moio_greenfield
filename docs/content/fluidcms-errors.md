---
title: "Fluidcms Error Handling"
slug: "fluidcms-errors"
category: "integrations"
order: 6
status: "published"
summary: "- ValidationError if tenant already has a home page"
tags: ["fluidcms"]
---

## Overview

- ValidationError if tenant already has a home page

# fluidcms - Failures

## Explicit Error Handling

### FluidPage

- ValidationError if tenant already has a home page

### FluidBlock

- ValidationError if block tenant doesn't match page tenant

### BlockBundle

- ValidationError if non-global without tenant
- ValidationError if global with tenant

### BlockBundleVersion

- ValidationError on invalid FSM transitions
- ValidationError on manifest modification of non-draft version
- Validation errors returned on publish without skip_validation

### BundleInstall

- ValidationError if tenant already has active installation of bundle
- ValidationError if bundle version not published

### Like

- ValidationError if message not from same session

### ConversationMessage

- ValidationError if user message has suggestions
- ValidationError if assistant suggestions not a list

### Block Payload Validation

- ValidationError on invalid block_type
- ValidationError on missing required fields per block type
- ValidationError on invalid action types
- ValidationError on missing action-specific fields

## Expected Failure Modes

- Duplicate page slugs
- Invalid block configurations
- Bundle validation failures
- FSM transition errors
