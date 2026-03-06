---
title: "Fluidcms Rules & Constraints"
slug: "fluidcms-rules"
category: "integrations"
order: 5
status: "published"
summary: "- (tenant, slug) unique - Only one is_home per tenant"
tags: ["fluidcms"]
---

## Overview

- (tenant, slug) unique - Only one is_home per tenant

# fluidcms - Invariants

## Enforced Rules

### FluidPage

- (tenant, slug) unique
- Only one is_home per tenant

### FluidBlock

- Block must belong to same tenant as page

### Conversation

- (session, topic, conversation_date) unique

### ConversationMessage

- (conversation, conversation_sequence) unique
- (session, session_sequence) unique
- User messages cannot have suggestions
- Assistant suggestions must be a list

### Like

- (session, message_index) unique
- Message must be from same session

### Article

- (tenant, slug) unique

### ArticleCategory

- (tenant, slug) unique

### ArticleTag

- (tenant, slug) unique

### BlockBundle

- slug unique globally
- Non-global bundles must have tenant
- Global bundles cannot have tenant

### BlockBundleVersion

- (bundle, version) unique

### BlockDefinition

- (bundle_version, block_type_id) unique

### BundleInstall

- Only one active installation per bundle per tenant
- Only published versions can be installed

### PageVersion

- (page, version_number) unique
