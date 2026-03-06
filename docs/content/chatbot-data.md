---
title: "Chatbot Data Model"
slug: "chatbot-data"
category: "chatbot"
order: 4
status: "published"
summary: "- id: UUID (PK) - enabled: BooleanField - name: CharField (unique per tenant) - model: CharField (default: \"chat-gpt-4o\") - instructions: TextField - channel: CharField (whatsapp, email, webhook, desk"
tags: ["chatbot"]
---

## Overview

- id: UUID (PK) - enabled: BooleanField - name: CharField (unique per tenant) - model: CharField (default: "chat-gpt-4o") - instructions: TextField - channel: CharField (whatsapp, email, webhook, desk

# chatbot - Data

## Owned Data Models

### AgentConfiguration

- id: UUID (PK)
- enabled: BooleanField
- name: CharField (unique per tenant)
- model: CharField (default: "chat-gpt-4o")
- instructions: TextField
- channel: CharField (whatsapp, email, webhook, desktop, web, flows)
- channel_id: CharField
- tools: JSONField (list)
- enable_websearch: BooleanField
- handoffs: M2M → self (asymmetric)
- default: BooleanField (unique true per tenant)
- model_settings: JSONField
- tenant: FK → Tenant

Constraints:
- `unique_default_agent_per_tenant`
- `unique_agent_name_per_tenant`

### ChatbotSession

- session: CharField (PK, unique, UUID string)
- id: UUIDField
- contact: FK → crm.Contact
- start, end, last_interaction: DateTimeField
- started_by: CharField
- context: JSONField
- final_summary: TextField
- channel: CharField
- active: BooleanField
- busy: BooleanField
- multi_message: BooleanField
- experience: CharField
- human_mode: BooleanField
- thread_id: CharField
- assistant_id: CharField
- agent_id: UUIDField
- csat: IntegerField
- current_agent: CharField
- agent_input_thread: TextField
- tenant: FK → Tenant

### ChatbotMemory

- session: FK → ChatbotSession
- role: CharField
- content: TextField
- created: DateTimeField
- intent: TextField
- subject_of_interest: CharField
- stitches: IntegerField
- skipped: IntegerField
- author: CharField

### ChatbotAssistant

- id: UUID (PK)
- openai_assistant_id: CharField
- name: CharField (unique per tenant)
- description: CharField
- instructions: TextField
- model: CharField
- file_search: BooleanField
- code_interpreter: BooleanField
- functions: TextField
- json_object: BooleanField
- temperature: FloatField
- top_p: FloatField
- default: BooleanField
- tenant: FK → Tenant

## External Data Read

- crm.Contact
- portal.Tenant
- portal.TenantConfiguration

## External Data Written

- Emits events via `moio_platform.core.events.emit_event`
