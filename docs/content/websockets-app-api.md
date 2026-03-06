---
title: "Websockets App API"
slug: "websockets-app-api"
category: "api-reference"
order: 2
status: "published"
summary: "- `ws/tickets/` - Real-time ticket updates"
tags: ["websockets_app"]
---

## Overview

- `ws/tickets/` - Real-time ticket updates

# websockets_app - Interfaces

## WebSocket Endpoints

### Ticket Updates

- `ws/tickets/` - Real-time ticket updates

### WhatsApp Notifications

- `ws/whatsapp/` - Real-time WhatsApp message notifications

### Campaign Stats

- `ws/campaigns/<campaign_id>/` - Real-time campaign statistics

### Flow Preview

- `ws/flows/<flow_id>/preview/stream/` - Real-time flow execution preview streaming

### Desktop CRM Agent

- `ws/crm-agent/` - Real-time CRM agent interaction

## Events Emitted

WebSocket messages (not flow events).

## Events Consumed

Consumer-specific updates from Redis channel layer.

## Input/Output Schemas

Specific message formats per consumer (not explicitly defined in routing).
