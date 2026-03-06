---
title: "Security Error Handling"
slug: "security-errors"
category: "api-reference"
order: 6
status: "published"
summary: "- AuthenticationFailed on invalid token - AuthenticationFailed on expired token - AuthenticationFailed on invalid signature - AuthenticationFailed on missing required claims"
tags: ["security"]
---

## Overview

- AuthenticationFailed on invalid token - AuthenticationFailed on expired token - AuthenticationFailed on invalid signature - AuthenticationFailed on missing required claims

# security - Failures

## Explicit Error Handling

### ServiceJWTAuthentication

- AuthenticationFailed on invalid token
- AuthenticationFailed on expired token
- AuthenticationFailed on invalid signature
- AuthenticationFailed on missing required claims

## Expected Failure Modes

- Token expiration
- Invalid token signature
- Missing SERVICE_TOKEN_SECRET
- Clock skew beyond tolerance
