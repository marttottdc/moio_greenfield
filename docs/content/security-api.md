---
title: "Security API"
slug: "security-api"
category: "api-reference"
order: 2
status: "published"
summary: "None (internal authentication mechanism)."
tags: ["security"]
---

## Overview

None (internal authentication mechanism).

# security - Interfaces

## Public Endpoints

None (internal authentication mechanism).

## Authentication Backend

`security.authentication.ServiceJWTAuthentication` - DRF authentication class for service tokens.

## Events Emitted

None.

## Events Consumed

None.

## Input/Output Schemas

### Service Token JWT Payload

```json
{
  "iss": "service_name",
  "sub": "service:service_name",
  "aud": "moio_platform",
  "scopes": ["scope1", "scope2"],
  "iat": 1234567890,
  "nbf": 1234567889,
  "exp": 1234654290,
  "tenant_id": "uuid (optional)"
}
```
