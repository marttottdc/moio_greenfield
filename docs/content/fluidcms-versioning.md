---
title: "Fluidcms Versioning"
slug: "fluidcms-versioning"
category: "integrations"
order: 8
status: "published"
summary: "- version_number: PositiveIntegerField - Auto-incremented per page"
tags: ["fluidcms"]
---

## Overview

- version_number: PositiveIntegerField - Auto-incremented per page

# fluidcms - Versioning

## Version Identifiers

### PageVersion

- version_number: PositiveIntegerField
- Auto-incremented per page

### BlockBundleVersion

- version: CharField (semantic versioning, e.g., "1.0.0", "1.2.3-beta")

## Compatibility Mechanisms

### BlockBundleVersion

- compatibility_range: JSONField
- Example: {"min_version": "1.0.0", "max_version": "2.0.0"}

### PageVersion

- content_pins: JSONField for pinned content references at publish time

## Migration Signals

- BlockBundleVersion lifecycle: draft → submitted → published → deprecated
