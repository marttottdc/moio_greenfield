---
title: "Recruiter Lifecycle"
slug: "recruiter-lifecycle"
category: "crm"
order: 3
status: "published"
summary: "- App config registered via `RecruiterConfig` - No explicit ready signals"
tags: ["recruiter"]
---

## Overview

- App config registered via `RecruiterConfig` - No explicit ready signals

# recruiter - Lifecycle

## Startup Behavior

- App config registered via `RecruiterConfig`
- No explicit ready signals

## Runtime Behavior

### CV Import Flow

```
import_buscojobs_candidates() [Celery beat]
  │
  ├── For each tenant:
  │   │
  │   ├── Process .zip files (read=False):
  │   │   ├── unzip_file()
  │   │   │   └── Extract to individual RecruiterDocuments
  │   │   └── Mark zip as read
  │   │
  │   └── Process .pdf files (read=False):
  │       ├── read_pdf_file()
  │       │   │
  │       │   ├── ocr_buscojobs_cv_files()
  │       │   │   └── BuscoJobs API extraction
  │       │   │
  │       │   ├── Process extracted data:
  │       │   │   ├── process_datos_personales()
  │       │   │   ├── process_experiencia_laboral()
  │       │   │   ├── process_educacion()
  │       │   │   ├── process_self_summary()
  │       │   │   └── process_overall_knowledge()
  │       │   │
  │       │   ├── Create/update Contact (crm)
  │       │   │
  │       │   ├── Create/update Candidate:
  │       │   │   ├── Get by document_id
  │       │   │   ├── Update CV fields
  │       │   │   ├── Save profile picture
  │       │   │   └── Inherit tags from document
  │       │   │
  │       │   └── Log errors to doc.error
  │       │
  │       └── Mark pdf as read
```

### Candidate Processing Pipeline

```
1. CV Import
   └── Creates Candidate with full_cv_transcript
   
2. candidate_summary() [Celery beat]
   └── Generates recruiter_summary (400 chars)
   
3. candidate_embedding() [Celery beat]
   └── Generates embedding vector (requires summary)
   
4. geocode_candidates() [Celery beat]
   └── Sets latitude/longitude from address
   
5. branch_distance_evaluation() [Celery beat]
   └── Calculates distances, sets recommended_branch
   
6. import_psigma_data() [Celery beat]
   └── Imports psicotest_score (if WAITING_FOR_DATA)
```

### Job Matching Flow

```
candidate_matching(tenant_id, job_posting_id, ...)
  │
  ├── Load JobPosting
  ├── Get job_embedding from description
  │
  ├── Build candidate queryset:
  │   ├── Filter: tenant, recruiter_posting=0, job_posting=None
  │   ├── Filter: recruiter_status in ["A"]
  │   ├── Filter: distance_category in ["A"]
  │   ├── Filter: branch in job_posting.branch
  │   ├── Filter: created in date_range
  │   ├── Apply tag filters (include/exclude)
  │   │
  │   └── Annotate with embedding distances:
  │       ├── L2Distance('embedding', job_embedding)
  │       └── CosineDistance('embedding', job_embedding)
  │
  ├── Order by L2 distance, limit to top_n
  │
  └── For each matched candidate:
      ├── Update recruiter_posting = job_posting_id
      ├── Update job_posting = JobPosting
      └── Update recruiter_status = "M"
```

### Psigma Integration Flow

```
import_psigma_data() [Celery beat]
  │
  ├── For each Psigma-enabled tenant:
  │   │
  │   └── For each candidate with status WAITING_FOR_DATA:
  │       │
  │       ├── PsigmaApi.get_user_examinations(document_id)
  │       │
  │       └── For each "procesado" result:
  │           ├── Get ajuste (profile fit score)
  │           ├── Update psicotest_score
  │           └── Status → DATA_COMPLETE
```

## Shutdown Behavior

No explicit shutdown behavior.
