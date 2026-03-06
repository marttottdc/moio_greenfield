---
title: "Security Lifecycle"
slug: "security-lifecycle"
category: "api-reference"
order: 3
status: "published"
summary: "No explicit startup behavior defined."
tags: ["security"]
---

## Overview

No explicit startup behavior defined.

# security - Lifecycle

## Startup Behavior

No explicit startup behavior defined.

## Runtime Behavior

### Token Generation

ServiceToken.generate_token():
1. Builds JWT payload with iss, sub, aud, scopes, iat, nbf, exp
2. Optionally includes tenant_id
3. Signs with HS256 using SERVICE_TOKEN_SECRET
4. Stores token and computed expires_at
5. Returns token string

### Token Validation

ServiceJWTAuthentication:
1. Extracts Bearer token from Authorization header
2. Decodes JWT with SERVICE_TOKEN_SECRET
3. Validates iss, sub, aud, exp, nbf claims
4. Sets tenant context if tenant_id present
5. Returns service user object with scopes

## Shutdown Behavior

No explicit shutdown behavior defined.
