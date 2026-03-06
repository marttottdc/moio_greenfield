---
title: "Flows Versioning"
slug: "flows-versioning"
category: "flows"
order: 8
status: "published"
summary: "- Single incrementing version number per flow - Auto-incremented in save() with row locking"
tags: ["flows"]
---

## Overview

- Single incrementing version number per flow - Auto-incremented in save() with row locking

# flows - Versioning

## Version Identifiers

### FlowVersion

- Single incrementing version number per flow
- Auto-incremented in save() with row locking

### FlowGraphVersion (LEGACY)

- major.minor versioning
- is_published flag
- preview_armed for draft testing

### FlowScriptVersion

- version_number per script
- published_at timestamp marks active version

## Compatibility Mechanisms

### FlowVersion Config

- config_schema: JSONField for schema definition
- config_values: JSONField for runtime values
- Persisted per version for determinism/replay-safety

### clone_as_draft()

Creates new draft version from existing version's graph and config.

## Migration Signals

- FlowGraphVersion is legacy; FlowVersion is current
- Flow.published_version reference replaces is_enabled pattern
