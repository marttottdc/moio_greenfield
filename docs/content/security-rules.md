---
title: "Security Rules & Constraints"
slug: "security-rules"
category: "api-reference"
order: 5
status: "published"
summary: "- Token signed with HS256 algorithm - Token audience must be \"moio_platform\" - Token expiration computed from duration_hours - nbf set to 1 second before iat to handle clock skew"
tags: ["security"]
---

## Overview

- Token signed with HS256 algorithm - Token audience must be "moio_platform" - Token expiration computed from duration_hours - nbf set to 1 second before iat to handle clock skew

# security - Invariants

## Enforced Rules

- Token signed with HS256 algorithm
- Token audience must be "moio_platform"
- Token expiration computed from duration_hours
- nbf set to 1 second before iat to handle clock skew
