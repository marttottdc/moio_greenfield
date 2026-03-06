---
title: "Recruiter API"
slug: "recruiter-api"
category: "crm"
order: 2
status: "published"
summary: "Internal views only (Django templates). No public REST API documented."
tags: ["recruiter"]
---

## Overview

Internal views only (Django templates). No public REST API documented.

# recruiter - Interfaces

## Public Endpoints

Internal views only (Django templates). No public REST API documented.

## Celery Tasks

### import_buscojobs_candidates
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Process uploaded CV documents
- **Flow**: 
  1. Unzip .zip files to individual documents
  2. Process .pdf files via BuscoJobs OCR
  3. Create/update candidates with extracted data

### geocode_candidates
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Geocode candidates without coordinates
- **Requires**: `google_integration_enabled` on tenant

### branch_distance_evaluation
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Calculate candidate distances to branches
- **Requires**: Candidate with lat/long, Google integration
- **Updates**: `recommended_branch`, `distance_to_branches`, `distance_evaluation_done`

### import_psigma_data
- **Queue**: `LOW_PRIORITY_Q`
- **Purpose**: Import psychometric test scores from Psigma
- **Requires**: `psigma_integration_enabled` on tenant
- **Updates**: `psicotest_score`, status transition

### candidate_embedding
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Purpose**: Generate embeddings for candidates
- **Requires**: `openai_integration_enabled`, non-empty `recruiter_summary`
- **Updates**: `embedding` vector field

### candidate_summary
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Purpose**: Generate AI summaries of candidates
- **Requires**: `openai_integration_enabled`
- **Updates**: `recruiter_summary` (400 char summary)

### candidate_matching
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Input**: `tenant_id`, `job_posting_id`, `min_psico`, `vacant_factor`, `date_range`
- **Purpose**: Match candidates to job posting
- **Uses**: pgvector for embedding similarity
- **Updates**: Candidate `recruiter_posting`, `job_posting`, `recruiter_status`

### wa_send_invitations
- **Queue**: `MEDIUM_PRIORITY_Q`
- **Input**: `invitees` list
- **Purpose**: Send WhatsApp invitations to candidates

## Events Emitted

None explicitly visible in code.

## Events Consumed

None explicitly visible in code.

## Input/Output Schemas

### Candidate Model

```python
{
    "id": UUID,
    "contact": UUID,  # crm.Contact
    "document_id": str,  # National ID
    "tenant": UUID,
    "source": str,
    "code": str,
    
    # CV Data
    "address": str,
    "postal_code": str,
    "city": str,
    "date_birth": date,
    "work_experience": dict,
    "education": dict,
    "self_summary": str,
    "overall_knowledge": dict,
    "full_cv_transcript": dict,
    
    # AI-Generated
    "recruiter_summary": str,  # 400 char summary
    "embedding": vector,  # pgvector
    
    # Location
    "latitude": float,
    "longitude": float,
    "recommended_branch": dict,
    "distance_to_branches": dict,
    "distance_evaluation_done": bool,
    
    # Status
    "recruiter_status": str,  # A, M, etc.
    "recruiter_posting": int,
    "job_posting": UUID,
    "psicotest_score": float,
    
    # Files
    "profile_picture": ImageField,
    "cv_file_doc": UUID,  # RecruiterDocument
    "tags": [UUID],
    
    "created": datetime,
    "reloaded": datetime
}
```

### JobPosting Model

```python
{
    "id": UUID,
    "tenant": UUID,
    "jp_id": str,
    "user": UUID,
    "name": str,
    "description": str,
    "status": str,  # "active", "closed", etc.
    "vacantes": int,
    "branch": [UUID],
    "salary": decimal,
    "max_age_cv": int,
    
    # Templates
    "invitation_template": str,
    "template_psicotest": str,
    
    # Tag Filtering
    "include_tags": [UUID],
    "exclude_tags": [UUID],
    
    "image": ImageField,
    "created": datetime,
    "updated": datetime
}
```

### RecruiterDocument Model

```python
{
    "id": UUID,
    "tenant": UUID,
    "user": UUID,
    "name": str,
    "file": FileField,
    "source": str,
    "batch": str,
    "read": bool,
    "error": str,
    "tags": [UUID],
    "created": datetime
}
```

### CandidateDistances Model

```python
{
    "id": UUID,
    "tenant": UUID,
    "candidate": UUID,
    "branch": UUID,
    "distance_category": str,  # "A", "B", "C", etc.
    "duration": int  # minutes
}
```
