---
title: "Datalab Overview"
slug: "datalab-overview"
category: "datalab"
order: 1
status: "published"
summary: "Data processing and analytics platform with file import, CRM data queries, and dataset versioning."
tags: ["datalab"]
---

## Overview

Data processing and analytics platform with file import, CRM data queries, and dataset versioning.

# datalab

## Responsibility

Data processing and analytics platform with file import, CRM data queries, and dataset versioning.

## What it Owns

- **FileAsset**: Uploaded files stored in S3
- **FileSet**: Collections of files for batch processing
- **Snapshot**: Point-in-time captures of processed data
- **ResultSet**: Processed data with schema and preview
- **DataSource**: Unified reference to various data types
- **ImportProcess/ImportRun**: Import workflow definitions and executions
- **Dataset/DatasetVersion**: Versioned dataset management
- **CRMView**: CRM data source queries
- **AnalyzerRun**: Analytics job tracking

## Core Components

### Import System (`imports/`)

#### ImportExecutor (`imports/services.py`)
Main import execution engine:
- `execute()`: Process file/fileset with import contract
- `_parse_file()`: CSV, Excel, PDF parsing
- `_apply_contract()`: Mapping, type casting, cleaning
- `_apply_dedupe()`: Deduplication strategies
- `_materialize_resultset()`: Parquet storage for large datasets

#### ImportProcessService (`imports/services.py`)
v3.1 control plane:
- `create_import_process()`: Define reusable import workflow
- `run_import_process()`: Execute with shape validation
- `clone_import_process()`: Version import definitions
- `execute_legacy_import()`: Backward compatibility bridge

#### Parsers (`imports/parsers.py`)
- `FileParser`: CSV, Excel parsing with configurable options
- `detect_schema()`: Automatic type inference

#### PDF Processing
- `PDFExtractor`: PDF text/table extraction
- `PDFShapeInspector`: Structure analysis
- `PdfShapeAnalyzer`: AI-assisted shape understanding

#### Shape Inspector (`imports/shape_inspector.py`)
- File structure detection
- Column type inference
- Shape fingerprinting for validation

### CRM Data Sources (`crm_sources/`)
- `CRMView`: Query definitions for CRM data
- `CRMQueryORMBuilder`: ORM query construction
- Registry of available CRM source types

### Storage (`core/storage.py`)
- S3 parquet storage
- File retrieval and caching

## Using DataLab from Flows

Flows orchestrate Data Lab through dedicated nodes (see flows-overview: Data Lab node catalog):

- **datalab_ingest**: Create a FileAsset from a URL, base64 content, or pass through an existing `file_id`.
- **datalab_file_adapter**: Execute an ImportProcess to produce a ResultSet from a file or fileset.
- **datalab_resultset_get**: Read ResultSet metadata and optional preview (works for ephemeral ResultSets that the REST API fences).
- **datalab_promote**: Promote a ResultSet to a Dataset (create or new version).

Flow Scripts can consume ResultSet data without DB access: use `input_payload` with `$datalab_resultset` references (e.g. `{"$datalab_resultset": {"id": "<uuid>", "mode": "preview", "limit": 200}}`). The backend resolves these (tenant-scoped, with row/byte limits) before the script runs.

## What it Does NOT Do

- Does not manage contacts (uses crm)
- Does not send notifications (uses chatbot)
- Does not handle authentication (delegates to portal)
- Does not execute workflows (uses flows for orchestration)
