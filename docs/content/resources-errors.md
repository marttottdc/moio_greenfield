---
title: "Resources Error Handling"
slug: "resources-errors"
category: "api-reference"
order: 6
status: "published"
summary: "- Returns empty results (403) if tenant not available"
tags: ["resources"]
---

## Overview

- Returns empty results (403) if tenant not available

# resources - Failures

## Explicit Error Handling

### Contact Search

- Returns empty results (403) if tenant not available

### WhatsApp Templates

- Returns 503 if WhatsApp client not available
- Returns 404 if template not found
- Returns error from WhatsApp API on test send failure

## Expected Failure Modes

- Missing tenant context
- WhatsApp integration not enabled
- WhatsApp API failures
