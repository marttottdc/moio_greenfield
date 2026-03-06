---
title: "Recruiter Error Handling"
slug: "recruiter-errors"
category: "crm"
order: 6
status: "published"
summary: "- Contact creation failure: Error logged to `doc.error` - Candidate update/create exception: Error logged to `doc.error` - Profile picture save failure: Sets `profile_picture = None`, continues - Gene"
tags: ["recruiter"]
---

## Overview

- Contact creation failure: Error logged to `doc.error` - Candidate update/create exception: Error logged to `doc.error` - Profile picture save failure: Sets `profile_picture = None`, continues - Gene

# recruiter - Failures

## Explicit Error Handling

### read_pdf_file
- Contact creation failure: Error logged to `doc.error`
- Candidate update/create exception: Error logged to `doc.error`
- Profile picture save failure: Sets `profile_picture = None`, continues
- Generic exception: Logged to `doc.error`

### geocode_candidates
- Geocoding errors: Silently skipped (candidate not updated)
- Missing Google API key: Tenant skipped

### branch_distance_evaluation
- Distance calculation exception: Logged, continues to next candidate
- Missing coordinates: Candidate skipped (filter on latitude__isnull=False)

### import_psigma_data
- API errors: Silently handled
- No examinations: No updates made

### candidate_embedding
- Missing summary: Candidate skipped (filter on recruiter_summary__exact="")
- OpenAI API error: Result is None, embedding not saved

### candidate_summary
- OpenAI API error: Summary may be empty
- Missing data: Summary generated from available fields

### candidate_matching
- JobPosting.DoesNotExist: Raises RuntimeError
- No OpenAI integration: Returns None
- No candidates found: Returns None
- Empty embedding result: Returns early

## Expected Failure Modes

### OCR Failures
- BuscoJobs API unavailable
- Malformed CV structure
- Missing required fields

### External API Failures
- Google Maps geocoding errors
- OpenAI API rate limits/errors
- Psigma API authentication failures

### Data Quality Issues
- Invalid phone numbers
- Duplicate document_id entries
- Missing profile pictures
- Corrupted zip files

## Recovery Mechanisms

### Document Reprocessing
- `reset_documents_status()`: Resets `read=False` for retry
- Clears error field for fresh attempt

### Distance Recalculation
- `delete_candidate_distances()`: Clear all distances for tenant
- Sets `distance_evaluation_done=False` for all candidates
- Allows full recalculation

### Batch Processing
- Tasks process all eligible records
- Failures in one record don't stop processing
- Error logged but iteration continues
