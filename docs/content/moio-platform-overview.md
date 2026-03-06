---
title: "Moio Platform Overview"
slug: "moio-platform-overview"
category: "api-reference"
order: 1
status: "published"
summary: "Core platform infrastructure providing settings, URL routing, ASGI/WSGI configuration, authentication, middleware, and event system."
tags: ["moio_platform"]
---

## Overview

Core platform infrastructure providing settings, URL routing, ASGI/WSGI configuration, authentication, middleware, and event system.

# moio_platform

## Responsibility

Core platform infrastructure providing settings, URL routing, ASGI/WSGI configuration, authentication, middleware, and event system.

## What it Owns

- Django settings and configuration
- URL routing (global)
- ASGI application configuration
- WSGI application configuration
- Celery application configuration
- Custom authentication backends
- Middleware (HTMX login required)
- Core views (error handlers)
- Health check endpoint
- Event system (emitter, router, schemas, snapshots)
- Storage backends (S3)
- Example snippets

## What it Does NOT Do

- Does not define domain models (delegates to apps)
- Does not implement business logic (delegates to apps)
