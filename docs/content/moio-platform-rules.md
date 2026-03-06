---
title: "Moio Platform Rules & Constraints"
slug: "moio-platform-rules"
category: "api-reference"
order: 5
status: "published"
summary: "- JWT access tokens valid for 60 minutes - Refresh tokens valid for 7 days - Service tokens validated against SERVICE_TOKEN_SECRET"
tags: ["moio_platform"]
---

## Overview

- JWT access tokens valid for 60 minutes - Refresh tokens valid for 7 days - Service tokens validated against SERVICE_TOKEN_SECRET

# moio_platform - Invariants

## Enforced Rules

### Authentication

- JWT access tokens valid for 60 minutes
- Refresh tokens valid for 7 days
- Service tokens validated against SERVICE_TOKEN_SECRET

### Security

- HTTPS required (SECURE_PROXY_SSL_HEADER)
- HSTS enabled (31536000 seconds)
- CORS restricted to specific origins
- CSRF protection enabled

### Data Upload

- Maximum 20 MB request body size
