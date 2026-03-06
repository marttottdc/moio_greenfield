---
title: "Moio Platform Lifecycle"
slug: "moio-platform-lifecycle"
category: "api-reference"
order: 3
status: "published"
summary: "- Loads environment from .env - Configures database from DATABASE_URL - Configures Redis for Celery broker and cacheops - Configures AWS S3 for static/media storage - Sets up logging (console, optiona"
tags: ["moio_platform"]
---

## Overview

- Loads environment from .env - Configures database from DATABASE_URL - Configures Redis for Celery broker and cacheops - Configures AWS S3 for static/media storage - Sets up logging (console, optiona

# moio_platform - Lifecycle

## Startup Behavior

### Settings Load

- Loads environment from .env
- Configures database from DATABASE_URL
- Configures Redis for Celery broker and cacheops
- Configures AWS S3 for static/media storage
- Sets up logging (console, optional Logtail)
- Prints debug/production mode warning
- Prints app version

### ASGI Configuration

- Channels routing with Redis layer
- WebSocket support via websocket_urlpatterns

### Celery Configuration

- Broker: Redis
- Result backend: Django DB
- Named queues: default, flows, HIGH/MEDIUM/LOW priority
- Task routes for flows and datalab

## Runtime Behavior

### Authentication

- JWT authentication via SimpleJWT
- Tenant-aware token serializer
- Service JWT authentication for service-to-service calls

### Middleware Stack

1. CorsMiddleware
2. CommonMiddleware
3. SecurityMiddleware
4. WhiteNoiseMiddleware
5. SessionMiddleware
6. LocaleMiddleware
7. AccountMiddleware (allauth)
8. CsrfViewMiddleware
9. AuthenticationMiddleware
10. MessageMiddleware
11. XFrameOptionsMiddleware
12. TenantMiddleware
13. HtmxMiddleware

### Event System

- Events emitted via emit_event()
- Events persisted to EventLog
- Events routed to matching flows

## Shutdown Behavior

No explicit shutdown behavior defined.
