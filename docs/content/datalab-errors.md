---
title: "Datalab Error Handling"
slug: "datalab-errors"
category: "datalab"
order: 6
status: "published"
summary: "- Missing file: Returns 400 with \"file field is required\" - File too large: Returns 400 with size error - S3 save failure: Returns 500 with \"Failed to save file\""
tags: ["datalab"]
---

## Overview

- Missing file: Returns 400 with "file field is required" - File too large: Returns 400 with size error - S3 save failure: Returns 500 with "Failed to save file"

# datalab - Failures

## Explicit Error Handling

### FileAssetViewSet.create
- Missing file: Returns 400 with "file field is required"
- File too large: Returns 400 with size error
- S3 save failure: Returns 500 with "Failed to save file"

### FileAssetViewSet.download
- File not in storage: Returns 404 with storage_key details
- Download error: Returns 500 with error details

### ImportViewSet.preview / execute
- FileAsset.DoesNotExist: Returns 404 "File not found"
- FileSet.DoesNotExist: Returns 404 "FileSet not found"
- FileParserError: Returns 400 with error message
- ImportContractValidationError: Returns 400 with error
- Generic exception: Returns 500 with details

### ImportExecutor
- Invalid contract: Raises `ImportExecutorError`
- File download failure: Raises `ImportExecutorError`
- Unsupported parser type: Raises `ImportExecutorError`
- Merge without dedupe_keys: Raises `ImportExecutorError`

### ImportProcessService
- Shape validation failure: Creates failed ImportRun
- Shape mismatch: ImportRun.status = "failed"
- Execution error: ImportRun.status = "failed" with error_message

## Expected Failure Modes

### S3 Failures
- Upload failures
- Download timeouts
- Permission errors
- Object not found

### Parsing Failures
- Invalid CSV encoding
- Corrupted Excel files
- PDF extraction errors
- Column type inference failures

### Database Failures
- Connection errors
- Transaction conflicts
- Foreign key violations

## Recovery Mechanisms

### Automatic Recovery
- Transaction rollback for atomic operations
- Temp directory cleanup in finally block

### Manual Recovery
- Re-upload failed files
- Re-run import with corrected contract
- Check ImportRun.shape_match for validation details

### Idempotency
- FileAsset upload generates unique key
- ImportRun creates new record each execution
- ResultSet IDs returned for reference
