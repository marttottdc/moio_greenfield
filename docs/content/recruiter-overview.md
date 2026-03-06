---
title: "Recruiter Overview"
slug: "recruiter-overview"
category: "crm"
order: 1
status: "published"
summary: "Applicant tracking system (ATS) with CV processing, candidate management, job posting matching, and psychometric test integration."
tags: ["recruiter"]
---

## Overview

Applicant tracking system (ATS) with CV processing, candidate management, job posting matching, and psychometric test integration.

# recruiter

## Responsibility

Applicant tracking system (ATS) with CV processing, candidate management, job posting matching, and psychometric test integration.

## What it Owns

- **Candidate**: Applicant records with CV data, embeddings, status tracking
- **CandidateDraft**: Draft candidate records
- **JobPosting**: Job position definitions with requirements and matching config
- **RecruiterDocument**: CV and supporting document storage
- **CandidateList**: Candidate grouping for workflows
- **CandidateDistances**: Distance calculations to branches
- **CandidateInterviewNotes**: Interview notes tracking
- **CandidateEvaluation**: Evaluation scores and assessments
- **Employee**: Hired employee records

## Core Components

### CV Processing (`tasks.py`)

#### BuscoJobs OCR Integration
- `read_pdf_file()`: Extract data from BuscoJobs CVs
- Extracts: name, contact info, work experience, education, knowledge
- Profile picture extraction and storage
- Tags inherited from source document

#### Candidate Data Extraction
- `process_datos_personales()`: Personal information
- `process_experiencia_laboral()`: Work experience
- `process_educacion()`: Education history
- `process_self_summary()`: Self-presentation
- `process_overall_knowledge()`: Skills and knowledge

### Candidate Processing (`tasks.py`)

#### Geocoding
- `geocode_candidates()`: Geocode candidate addresses via Google Maps
- Uses tenant's Google API key

#### Distance Evaluation
- `branch_distance_evaluation()`: Calculate distances to branches
- `candidate_distance_to_branches_evaluation_v2()`: Detailed distance analysis
- Stores recommended branch and distance categories

### AI Integration (`tasks.py`)

#### Embeddings
- `candidate_embedding()`: Generate embeddings for similarity search
- Uses MoioOpenai with tenant's API key

#### Summaries
- `candidate_summary()`: AI-generated candidate summaries (400 chars)
- Emphasizes recent experience and education

### Candidate Matching (`tasks.py`)

#### Job Matching
- `candidate_matching()`: Match candidates to job postings
- Filters: status, distance, tags, date range
- Embedding similarity via pgvector (L2Distance, CosineDistance)
- Updates candidate status to "M" (Matched)

### External Integrations

#### Psigma Integration (`tasks.py`)
- `import_psigma_data()`: Import psychometric test results
- Updates candidate psicotest_score
- Status transition: WAITING_FOR_DATA → DATA_COMPLETE

## Candidate Status Flow

```
NEW (implicit)
  │
  ├── CV imported
  │
  ▼
A - Available
  │
  ├── candidate_matching()
  │
  ▼
M - Matched (to job posting)
  │
  ├── Interview/Evaluation
  │
  ▼
(Various terminal states)
```

## What it Does NOT Do

- Does not handle authentication (delegates to portal)
- Does not send notifications (uses chatbot/campaigns)
- Does not manage contacts directly (creates via crm)
- Does not run workflows (uses flows)
