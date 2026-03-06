---
title: "Security Overview"
slug: "security-overview"
category: "api-reference"
order: 1
status: "published"
summary: "Service-to-service authentication and authorization with JWT tokens and scope-based access control."
tags: ["security"]
---

## Overview

Service-to-service authentication and authorization with JWT tokens and scope-based access control.

# security

## Responsibility

Service-to-service authentication and authorization with JWT tokens and scope-based access control.

## What it Owns

- **ServiceToken**: Service-to-service authentication tokens with scopes

## Core Components

### ServiceToken Model
- UUID-based tokens with auto-generated JWT
- Scope-based permissions (e.g., "pages.read", "tenant.config.read")
- Optional tenant restriction
- Configurable duration (default 24 hours)
- Active/inactive status

### Authentication (`authentication.py`)
- JWT token verification
- Scope validation
- Tenant context extraction

### Permissions (`permissions.py`)
- Scope-based permission classes
- Integration with DRF permission system

## Token Structure

```python
{
    "iss": "service_name",      # Service issuer
    "sub": "service:name",      # Subject
    "aud": "moio_platform",     # Audience
    "scopes": ["pages.read"],   # Allowed scopes
    "tenant_id": "optional",    # Tenant restriction
    "iat": int,                 # Issued at
    "nbf": int,                 # Not before (iat - 1)
    "exp": int                  # Expiration
}
```

## Token Generation Flow

```
ServiceToken.generate_token()
  │
  ├── Build payload with scopes
  ├── Add tenant_id if restricted
  │
  ├── jwt.encode(payload, SECRET, HS256)
  │
  ├── Set expires_at
  │
  └── Save and return token
```

## What it Does NOT Do

- Does not handle user authentication (see portal JWT)
- Does not manage user permissions (see portal RBAC)
- Does not validate webhook signatures (see crm webhooks)
