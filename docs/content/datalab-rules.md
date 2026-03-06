---
title: "Datalab Rules & Constraints"
slug: "datalab-rules"
category: "datalab"
order: 5
status: "published"
summary: "- FileAsset must have `tenant` (tenant-scoped) - `storage_key` must be valid S3 path - Size limited to 100MB at upload"
tags: ["datalab"]
---

## Overview

- FileAsset must have `tenant` (tenant-scoped) - `storage_key` must be valid S3 path - Size limited to 100MB at upload

# datalab - Invariants

## Data Integrity Rules

### FileAsset Rules
- FileAsset must have `tenant` (tenant-scoped)
- `storage_key` must be valid S3 path
- Size limited to 100MB at upload

### FileSet Rules
- FileSet must have `tenant` (tenant-scoped)
- Files can belong to multiple FileSets (M2M)
- `last_snapshot` tracks most recent processing

### ResultSet Rules
- ResultSet must have `tenant` (tenant-scoped)
- Origin must be: import, crm_query, analyzer
- Storage must be: memory, parquet
- `preview_json` limited to 200 rows
- Fencing: ephemeral non-analyzer ResultSets not directly accessible

### ImportProcess Rules
- ImportProcess must have `tenant` (tenant-scoped)
- Version auto-incremented per (tenant, name) combination
- `shape_fingerprint` used for validation

### Dataset Rules
- Dataset must have `tenant` (tenant-scoped)
- Name unique per tenant
- `current_version` tracks promoted version

## Business Logic Constraints

### Import Contract Validation
- Pydantic schema validation before execution
- Date format conversion (DD/MM/YYYY → %d/%m/%Y)
- Type casting: integer, decimal, boolean, date, datetime, string

### Accumulation Strategies
- **append**: Concatenate new data after existing
- **merge**: Deduplicate on keys, prefer new values

### Dedupe Strategies
- **keep_first**: First occurrence wins
- **keep_last**: Last occurrence wins
- **reject**: Remove all duplicates

### Materialization Threshold
- ResultSets with > 10,000 rows auto-materialized to Parquet
- Parquet storage uses S3 with computed key
