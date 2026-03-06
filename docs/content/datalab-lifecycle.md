---
title: "Datalab Lifecycle"
slug: "datalab-lifecycle"
category: "datalab"
order: 3
status: "published"
summary: "- App config registered via `DatalabConfig` - No explicit ready signals"
tags: ["datalab"]
---

## Overview

- App config registered via `DatalabConfig` - No explicit ready signals

# datalab - Lifecycle

## Startup Behavior

- App config registered via `DatalabConfig`
- No explicit ready signals

## Runtime Behavior

### File Upload Flow

```
POST /api/v1/datalab/files/
  │
  ├── Validate file size (max 100MB)
  │
  ├── Generate unique storage key
  │
  ├── Upload to S3 via default_storage.save()
  │
  ├── Detect metadata:
  │   ├── CSV: Parse headers, estimate rows
  │   └── Excel: Get sheet names
  │
  └── Create FileAsset record
```

### Import Execution Flow (Legacy)

```
ImportExecutor.execute(source, contract_json, ...)
  │
  ├── Validate contract via Pydantic
  ├── Compute contract hash
  │
  ├── Process source:
  │   │
  │   ├── FileSet:
  │   │   ├── Check last snapshot for incremental
  │   │   ├── Find new files
  │   │   ├── Parse new files
  │   │   └── Merge with base (append or merge strategy)
  │   │
  │   └── Single File:
  │       └── Parse according to parser config
  │
  ├── Apply contract (mapping, types, cleaning)
  │
  ├── Apply dedupe if configured
  │
  ├── Create ResultSet:
  │   ├── Detect schema
  │   ├── Store preview (first 200 rows)
  │   └── Materialize to parquet if > 10k rows
  │
  └── Create Snapshot + AccumulationLog (for FileSet)
```

### ImportProcess Flow (v3.1)

```
ImportProcessService.run_import_process(process, raw_dataset)
  │
  ├── Inspect file shape
  │
  ├── Validate shape match (fail-fast):
  │   └── Compare fingerprint
  │       └── Mismatch? → Create failed ImportRun
  │
  ├── Extract structural units:
  │   └── Parse file with contract parser config
  │
  ├── Apply semantic derivations:
  │   └── Transform via mapping rules
  │
  ├── Create ResultSet(s)
  │
  └── Create ImportRun (success or failed)
```

### Dataset Versioning Flow

```
Dataset.create_version(resultset_id)
  │
  ├── Increment version number
  ├── Create DatasetVersion linking ResultSet
  └── Optionally promote to current
```

## Shutdown Behavior

No explicit shutdown behavior.
