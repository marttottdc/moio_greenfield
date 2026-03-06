---
title: "Moio Platform Error Handling"
slug: "moio-platform-errors"
category: "api-reference"
order: 6
status: "published"
summary: "- handler400 - Bad Request - handler403 - Forbidden - handler404 - Not Found - handler500 - Internal Server Error"
tags: ["moio_platform"]
---

## Overview

- handler400 - Bad Request - handler403 - Forbidden - handler404 - Not Found - handler500 - Internal Server Error

# moio_platform - Failures

## Explicit Error Handling

### Custom Error Handlers

- handler400 - Bad Request
- handler403 - Forbidden
- handler404 - Not Found
- handler500 - Internal Server Error

### Cache Degradation

- CACHEOPS_DEGRADE_ON_FAILURE = True (graceful Redis failure)

## Expected Failure Modes

- Database connection failures
- Redis connection failures
- S3 storage failures
- Authentication failures
