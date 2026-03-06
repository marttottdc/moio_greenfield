---
title: "Recruiter Rules & Constraints"
slug: "recruiter-rules"
category: "crm"
order: 5
status: "published"
summary: "- Candidate must have `tenant` (tenant-scoped) - `document_id` unique per tenant (national ID) - Linked to crm.Contact via ForeignKey - `embedding` generated from `recruiter_summary`"
tags: ["recruiter"]
---

## Overview

- Candidate must have `tenant` (tenant-scoped) - `document_id` unique per tenant (national ID) - Linked to crm.Contact via ForeignKey - `embedding` generated from `recruiter_summary`

# recruiter - Invariants

## Data Integrity Rules

### Candidate Rules
- Candidate must have `tenant` (tenant-scoped)
- `document_id` unique per tenant (national ID)
- Linked to crm.Contact via ForeignKey
- `embedding` generated from `recruiter_summary`

### JobPosting Rules
- JobPosting must have `tenant` (tenant-scoped)
- `vacantes` determines matching quota (vacant_factor multiplier)
- `branch` M2M defines target locations
- Tag filters (include/exclude) control candidate pool

### RecruiterDocument Rules
- Document must have `tenant` (tenant-scoped)
- `read` flag prevents reprocessing
- `error` field captures processing failures
- Tags inherited by created candidates

### CandidateDistances Rules
- One record per (candidate, branch) combination
- `distance_category` classifies proximity (A=close, etc.)
- `duration` in minutes for commute time

## Business Logic Constraints

### CV Processing
- Only unread documents processed
- BuscoJobs format expected for OCR
- Profile pictures extracted and stored
- Tags flow: Document → Candidate

### Embedding Generation
- Requires non-empty `recruiter_summary`
- Uses tenant's OpenAI configuration
- Model: Tenant's configured embedding model

### Matching Algorithm
- Candidates filtered by:
  - Status = "A" (Available)
  - Distance category = "A" (Close)
  - No existing job_posting
  - Within date_range days
  - Tag inclusion/exclusion rules
- Sorted by embedding similarity (L2 or Cosine)
- Limited to `vacantes * vacant_factor`

### Psigma Integration
- Only processes candidates with status WAITING_FOR_DATA
- Score from "procesado" examinations only
- Status transitions to DATA_COMPLETE on score receipt
