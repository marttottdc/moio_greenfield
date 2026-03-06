---
title: "Websockets App Data Model"
slug: "websockets-app-data"
category: "api-reference"
order: 4
status: "published"
summary: "None."
tags: ["websockets_app"]
---

## Overview

None.

# websockets_app - Data

## Owned Data Models

None.

## External Data Read

Data specific to each consumer:
- TicketUpdatesConsumer: crm.Ticket
- WhatsAppNotificationsConsumer: chatbot messages
- CampaignStatsConsumer: campaigns.Campaign statistics
- FlowPreviewConsumer: flows.Flow execution data
- DesktopCrmAgentConsumer: crm.Contact, chatbot.AgentConfiguration

## External Data Written

None directly (consumers are read/stream only).
