---
title: "Datalab API"
slug: "datalab-api"
category: "datalab"
order: 2
status: "published"
summary: "- `GET /api/v1/datalab/files/` - List file assets - `POST /api/v1/datalab/files/` - Upload file (max 100MB) - `GET /api/v1/datalab/files/{id}/` - Get file detail - `GET /api/v1/datalab/files/{id}/down"
tags: ["datalab"]
---

## Overview

- `GET /api/v1/datalab/files/` - List file assets - `POST /api/v1/datalab/files/` - Upload file (max 100MB) - `GET /api/v1/datalab/files/{id}/` - Get file detail - `GET /api/v1/datalab/files/{id}/down

# datalab - Interfaces

## Public API Endpoints

### Files
- `GET /api/v1/datalab/files/` - List file assets
- `POST /api/v1/datalab/files/` - Upload file (max 100MB)
- `GET /api/v1/datalab/files/{id}/` - Get file detail
- `GET /api/v1/datalab/files/{id}/download/` - Download file

### FileSets
- `GET /api/v1/datalab/filesets/` - List filesets
- `POST /api/v1/datalab/filesets/` - Create fileset
- `POST /api/v1/datalab/filesets/{id}/add-files/` - Add files to set

### Imports
- `POST /api/v1/datalab/imports/preview/` - Preview import
- `POST /api/v1/datalab/imports/execute/` - Execute import
- `POST /api/v1/datalab/imports/inspect-shape/` - Inspect file shape

### ImportProcess (v3.1)
- `GET /api/v1/datalab/import-processes/` - List processes
- `POST /api/v1/datalab/import-processes/` - Create process
- `POST /api/v1/datalab/import-processes/{id}/run/` - Execute process
- `POST /api/v1/datalab/import-processes/{id}/clone/` - Clone process
- `POST /api/v1/datalab/import-processes/inspect-shape/` - Shape inspection
- `POST /api/v1/datalab/import-processes/interpret-shape/` - AI interpretation

### ResultSets
- `GET /api/v1/datalab/resultsets/` - List resultsets
- `GET /api/v1/datalab/resultsets/{id}/` - Get resultset (fenced)
- `POST /api/v1/datalab/resultsets/{id}/materialize/` - Materialize to parquet

### Datasets
- `GET /api/v1/datalab/datasets/` - List datasets
- `POST /api/v1/datalab/datasets/` - Create dataset
- `POST /api/v1/datalab/datasets/{id}/create-version/` - Create version
- `POST /api/v1/datalab/datasets/{id}/promote-version/` - Promote to current

## Input/Output Schemas

### ImportContract (v1)

```python
{
    "version": "1",
    "parser": {
        "type": str,  # "csv" | "excel" | "pdf"
        "header_row": int,
        "skip_rows": int,
        "delimiter": str,  # For CSV
        "sheet": int | str,  # For Excel
        "structural_unit": str,  # For PDF
        "date_format": str,  # e.g., "DD/MM/YYYY"
        "datetime_format": str
    },
    "mapping": [
        {
            "source": str,
            "target": str,
            "type": str,  # "string" | "integer" | "decimal" | "boolean" | "date" | "datetime"
            "format": str,  # Optional, for dates
            "clean": [str]  # "trim" | "upper" | "lower" | "remove_accents" | "currency_to_decimal"
        }
    ],
    "dedupe": {
        "keys": [str],
        "strategy": str  # "keep_first" | "keep_last" | "reject"
    }
}
```

### FileAssetSerializer

```python
{
    "id": UUID,
    "storage_key": str,
    "filename": str,
    "content_type": str,
    "size": int,
    "uploaded_by": UUID,
    "metadata": {
        "detected_type": str,
        "row_count_estimate": int,
        "columns": [str],
        "sheet_names": [str]
    },
    "created_at": datetime
}
```

### ResultSetSerializer

```python
{
    "id": UUID,
    "name": str,
    "origin": str,  # "import" | "crm_query"
    "schema_json": {
        "columns": [
            {
                "name": str,
                "type": str,
                "nullable": bool
            }
        ]
    },
    "row_count": int,
    "storage": str,  # "memory" | "parquet"
    "storage_key": str | None,
    "preview_json": [dict],  # First 200 rows
    "is_json_object": bool,
    "lineage_json": dict,
    "created_at": datetime,
    "expires_at": datetime | None
}
```

### ImportProcess

```python
{
    "id": UUID,
    "name": str,
    "file_type": str,
    "shape_fingerprint": str,  # SHA256
    "shape_description": dict,
    "structural_units": [dict],
    "semantic_derivations": [dict],
    "contract_json": dict,  # ImportContract
    "version": int,
    "is_active": bool,
    "import_data_as_json": bool
}
```

### ImportRun

```python
{
    "id": UUID,
    "import_process": UUID,
    "raw_dataset": UUID,  # FileAsset
    "shape_match": {
        "status": str,  # "pass" | "fail" | "warn"
        "reasons": [str]
    },
    "status": str,  # "success" | "failed"
    "resultset_ids": [UUID],
    "error_message": str | None
}
```

### Dataset

```python
{
    "id": UUID,
    "name": str,  # Unique per tenant
    "description": str,
    "current_version": int,
    "created_by": UUID,
    "created_at": datetime,
    "updated_at": datetime
}
```
