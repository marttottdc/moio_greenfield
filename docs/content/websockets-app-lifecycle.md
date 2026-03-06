---
title: "Websockets App Lifecycle"
slug: "websockets-app-lifecycle"
category: "api-reference"
order: 3
status: "published"
summary: "WebSocket consumers registered via ASGI application at startup."
tags: ["websockets_app"]
---

## Overview

WebSocket consumers registered via ASGI application at startup.

# websockets_app - Lifecycle

## Startup Behavior

WebSocket consumers registered via ASGI application at startup.

## Runtime Behavior

### Connection Lifecycle

1. Client connects to WebSocket endpoint
2. Consumer.connect() authenticates and joins channel groups
3. Consumer receives messages via channel layer
4. Consumer sends messages to client
5. Client disconnects, Consumer.disconnect() cleans up

### Channel Layer

- Redis backend (`channels_redis.core.RedisChannelLayer`)
- Group-based messaging for broadcasts

## Shutdown Behavior

- Consumers disconnect from channel groups
- WebSocket connections closed gracefully
