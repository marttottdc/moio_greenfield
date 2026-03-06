---
title: "Fluidcms Overview"
slug: "fluidcms-overview"
category: "integrations"
order: 1
status: "published"
summary: "Content management system for marketing pages with visual block builder, visitor tracking, conversational interactions, and article publishing."
tags: ["fluidcms"]
---

## Overview

Content management system for marketing pages with visual block builder, visitor tracking, conversational interactions, and article publishing.

# fluidcms

## Responsibility

Content management system for marketing pages with visual block builder, visitor tracking, conversational interactions, and article publishing.

## What it Owns

- **FluidPage**: Tenant-scoped pages with status (draft, live, public, archive)
- **FluidBlock**: Content blocks with type, layout, config (header, hero, CTA, FAQ, testimonials, etc.)
- **FluidMedia**: Media asset storage (images, videos, documents)
- **Topic**: Content holder for blocks with marketing copy, benefits, features
- **VisitorSession**: Visitor tracking with UTM parameters
- **Conversation/ConversationMessage**: Chat sessions with topics
- **Article/ArticleCategory/ArticleTag**: Blog article publishing system
- **BlockBundle/BlockBundleVersion**: Designer-created block definitions with versioning
- **BlockDefinition**: Block templates with variants, toggles, style axes, content slots
- **BundleInstall**: Tenant bundle version installations
- **PageVersion**: Immutable page snapshots for versioning

## Core Components

### Page System
- FluidPage CRUD with slug uniqueness per tenant
- Block ordering and layout
- Status-based publishing workflow

### Block System
- 20+ block types (header, hero, rich_text, feature_list, CTA, blog, services, etc.)
- Block type validation via `validate_block_payload()`
- CTA action types: external_link, internal_link, scroll_to_anchor, topic_chat, etc.
- Hidden content for conversation initiators and agent instructions

### Bundle System (Block Builder)
- BlockBundle: Global or tenant-specific block collections
- BlockBundleVersion: Versioned with FSM lifecycle (DRAFT → SUBMITTED → PUBLISHED → DEPRECATED)
- BlockDefinition: Typed block templates with variants, toggles, style axes, content slots
- BundleInstall: Track installed versions per tenant

### Visitor Tracking
- VisitorSession: Track visitor engagement
- TopicVisit: Track page visits
- ConversationMessage: Chat messages with suggestions

### Article Repository
- Article: Blog posts with draft/published/archived status
- ArticleCategory: Hierarchical categories
- ArticleTag: Tagging system

## What it Does NOT Do

- Does not handle authentication (delegates to portal)
- Does not send messages (delegates to chatbot)
- Does not manage CRM contacts (delegates to crm)
