---
title: "Datalab Versioning"
slug: "datalab-versioning"
category: "datalab"
order: 8
status: "published"
summary: "- version: PositiveIntegerField - Unique per (tenant, name)"
tags: ["datalab"]
---

## Overview

- version: PositiveIntegerField - Unique per (tenant, name)

# datalab - Versioning

## Version Identifiers

### ImportProcess

- version: PositiveIntegerField
- Unique per (tenant, name)

### Snapshot

- version: PositiveIntegerField
- Unique per (tenant, name)

### DatasetVersion

- version_number: PositiveIntegerField
- Sequential per dataset

## Compatibility Mechanisms

None explicitly defined.

## Migration Signals

- Pipeline and PipelineRun models have been removed (use Flows for orchestration)
