---
title: "Authentication"
slug: "authentication"
category: "getting-started"
order: 2
status: "published"
summary: "Learn how to authenticate with the Moio Platform API using JWT tokens"
tags: ["security", "jwt", "tokens"]
---

## Overview

The Moio Platform API uses JWT (JSON Web Tokens) for authentication. This guide covers how to obtain, use, and refresh tokens.

## How It Works

```
┌─────────────┐     POST /auth/login/      ┌─────────────┐
│   Client    │ ─────────────────────────> │   Server    │
│             │ <───────────────────────── │             │
│             │     { access, refresh }    │             │
│             │                            │             │
│             │     GET /api/v1/...        │             │
│             │     Authorization: Bearer  │             │
│             │ ─────────────────────────> │             │
└─────────────┘                            └─────────────┘
```

## Getting Tokens

### Login Request

```bash
curl -X POST https://your-domain.com/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-password"
  }'
```

### Response

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNjg...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTY4..."
}
```

| Token | Lifetime | Purpose |
|-------|----------|---------|
| `access` | 5 minutes | Used for API requests |
| `refresh` | 24 hours | Used to get new access tokens |

## Using Tokens

Include the access token in the `Authorization` header:

```bash
curl https://your-domain.com/api/v1/crm/contacts/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
```

## Refreshing Tokens

When your access token expires, use the refresh token to get a new one:

```bash
curl -X POST https://your-domain.com/api/v1/auth/refresh/ \
  -H "Content-Type: application/json" \
  -d '{
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }'
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

## API Keys for Automated Services

For scripts, integrations, or headless services you can use a long-lived API key instead of short-lived JWT tokens. Each user can have **one active API key** at a time. Create and revoke it with JWT; use the key as a Bearer token for API calls.

### Create an API key

Authenticate with JWT, then POST to create (or replace) your API key:

```bash
curl -X POST https://your-domain.com/api/v1/auth/api-key/ \
  -H "Authorization: Bearer <your-jwt-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Integration"}'
```

Response (the plain key is shown **only once**):

```json
{
  "id": 1,
  "name": "My Integration",
  "key": "moio_abc123def456...",
  "masked_key": "moio_****...****",
  "created_at": "2025-01-15T12:00:00Z",
  "expires_at": null,
  "warning": "Save this key securely - it will not be shown again."
}
```

Store the `key` value securely; it cannot be retrieved again.

### Use the API key

Send it in the `Authorization` header like a JWT:

```bash
curl https://your-domain.com/api/v1/crm/contacts/ \
  -H "Authorization: Bearer moio_abc123def456..."
```

The key works for all API endpoints that accept Bearer authentication. Creating a new key revokes the previous one.

### Check key status

With JWT, GET the current key info (masked only):

```bash
curl https://your-domain.com/api/v1/auth/api-key/ \
  -H "Authorization: Bearer <your-jwt-access-token>"
```

Response includes `masked_key`, `created_at`, `last_used_at`, and `expires_at`.

### Revoke the API key

With JWT, DELETE to revoke:

```bash
curl -X DELETE https://your-domain.com/api/v1/auth/api-key/ \
  -H "Authorization: Bearer <your-jwt-access-token>"
```

You cannot use the API key itself to create, view, or revoke keys; use JWT for those actions.

## Error Handling

| Status | Error | Solution |
|--------|-------|----------|
| 401 | Token expired | Refresh the token |
| 401 | Invalid token | Re-authenticate |
| 403 | Permission denied | Check user permissions |

## Best Practices

1. **Never expose tokens** in URLs, logs, or client-side code
2. **Refresh proactively** before the token expires
3. **Use HTTPS** always in production
4. **Store securely** using httpOnly cookies or secure storage

## Code Examples

### Python

```python
import requests

class MoioClient:
    def __init__(self, base_url, email, password):
        self.base_url = base_url
        self.access_token = None
        self.refresh_token = None
        self._login(email, password)
    
    def _login(self, email, password):
        response = requests.post(
            f"{self.base_url}/api/v1/auth/login/",
            json={"email": email, "password": password}
        )
        tokens = response.json()
        self.access_token = tokens["access"]
        self.refresh_token = tokens["refresh"]
    
    def _refresh(self):
        response = requests.post(
            f"{self.base_url}/api/v1/auth/refresh/",
            json={"refresh": self.refresh_token}
        )
        self.access_token = response.json()["access"]
    
    def get(self, endpoint):
        response = requests.get(
            f"{self.base_url}{endpoint}",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        if response.status_code == 401:
            self._refresh()
            return self.get(endpoint)
        return response.json()
```

### JavaScript

```javascript
class MoioClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.accessToken = null;
    this.refreshToken = null;
  }

  async login(email, password) {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const tokens = await response.json();
    this.accessToken = tokens.access;
    this.refreshToken = tokens.refresh;
  }

  async request(endpoint, options = {}) {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${this.accessToken}`
      }
    });
    
    if (response.status === 401) {
      await this.refresh();
      return this.request(endpoint, options);
    }
    
    return response.json();
  }

  async refresh() {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: this.refreshToken })
    });
    const { access } = await response.json();
    this.accessToken = access;
  }
}
```
