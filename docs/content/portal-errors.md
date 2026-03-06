---
title: "Portal Error Handling"
slug: "portal-errors"
category: "integrations"
order: 6
status: "published"
summary: "- Invalid credentials: 401 Unauthorized - Expired token: 401 Unauthorized - Missing tenant: 403 Forbidden (for tenant-required endpoints)"
tags: ["portal"]
---

## Overview

- Invalid credentials: 401 Unauthorized - Expired token: 401 Unauthorized - Missing tenant: 403 Forbidden (for tenant-required endpoints)

# portal - Failures

## Explicit Error Handling

### Authentication
- Invalid credentials: 401 Unauthorized
- Expired token: 401 Unauthorized
- Missing tenant: 403 Forbidden (for tenant-required endpoints)

### Token Service
- Token refresh failure: Returns None/raises exception
- OAuth provider errors: Logged, sync disabled

### Integration Sync
- Provider API errors: Logged, continues
- Token expired and refresh fails: Account marked for re-auth
- Network errors: Celery retry (implicit)

## Expected Failure Modes

### OAuth Failures
- Token revoked by user
- Token expired and refresh failed
- Provider API changes
- Rate limiting

### Database Failures
- Tenant not found
- User not associated with tenant
- Configuration missing

### External Provider Failures
- Gmail API errors
- Outlook API errors
- IMAP connection failures
- Calendar sync errors

## Recovery Mechanisms

### Automatic Recovery
- OAuth token auto-refresh before expiration
- Sync tasks retry on transient failures
- Connection pooling for database

### Manual Recovery
- Re-authorize OAuth accounts
- Update integration credentials
- Check TenantConfiguration for missing values

### Tenant Tool Sync
- Scheduled on new tenant creation
- Can be re-triggered via management command
- Idempotent (get_or_create)
