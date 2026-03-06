---
title: "Quickstart Guide"
slug: "quickstart"
category: "getting-started"
order: 1
status: "published"
summary: "Get up and running with the Moio Platform API in 5 minutes"
tags: ["beginner", "setup"]
---

## Overview

This guide will help you make your first API call to the Moio Platform in under 5 minutes.

## Prerequisites

Before you begin, you'll need:

- A Moio Platform account
- Your login credentials (email and password)
- A tool to make HTTP requests (curl, Postman, or your programming language of choice)

## Steps

### Step 1: Get an Access Token

First, authenticate to get a JWT access token:

```bash
curl -X POST https://your-domain.com/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your@email.com",
    "password": "your-password"
  }'
```

You'll receive a response like:

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

Save the `access` token - you'll need it for all subsequent requests.

### Step 2: Make Your First API Call

Now use the token to fetch your contacts:

```bash
curl https://your-domain.com/api/v1/crm/contacts/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Step 3: Create a Contact

Let's create your first contact:

```bash
curl -X POST https://your-domain.com/api/v1/crm/contacts/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "fullname": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890"
  }'
```

## Next Steps

Now that you've made your first API calls, explore:

- [Authentication Guide](/docs/authentication) - Learn about token refresh and security
- [CRM API Reference](/docs/api-reference) - Full contact, ticket, and deal endpoints
- [Webhooks](/docs/webhooks) - Set up real-time notifications
