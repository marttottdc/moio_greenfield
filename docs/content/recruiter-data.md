---
title: "Recruiter Data Model"
slug: "recruiter-data"
category: "crm"
order: 4
status: "published"
summary: "- id: AutoField (PK) - file: FileField - name: CharField - read: BooleanField - error: TextField - user: CharField - source: CharField - batch: UUIDField - tags: M2M → crm.Tag - tenant: FK → Tenant"
tags: ["recruiter"]
---

## Overview

- id: AutoField (PK) - file: FileField - name: CharField - read: BooleanField - error: TextField - user: CharField - source: CharField - batch: UUIDField - tags: M2M → crm.Tag - tenant: FK → Tenant

# recruiter - Data

## Owned Data Models

### RecruiterDocument

- id: AutoField (PK)
- file: FileField
- name: CharField
- read: BooleanField
- error: TextField
- user: CharField
- source: CharField
- batch: UUIDField
- tags: M2M → crm.Tag
- tenant: FK → Tenant

### JobDescription

- id: AutoField (PK)
- name: CharField
- description: TextField
- rank: TextField
- salary_range: TextField
- embedding: TextField
- tenant: FK → Tenant

### JobPosting

- jp_id: UUIDField
- name: CharField
- description: TextField
- status: CharField
- branch: M2M → crm.Branch
- job_description: M2M → JobDescription
- vacantes: IntegerField
- start_date, closure_date, group_interview_date: DateTimeField
- psigma_link, calendar_link: CharField
- salary: IntegerField
- invitation_template, reminder_template, psicotest_template: TextField
- image: FileField
- publish: BooleanField
- user: FK → User
- max_age_cv: IntegerField
- include_tags, exclude_tags: M2M → crm.Tag
- tenant: FK → Tenant

### Candidate

- id: AutoField (PK)
- contact: FK → crm.Contact
- date_birth: DateField
- address, city, state, postal_code: CharField
- latitude, longitude: FloatField
- document_id: CharField
- work_experience, education: TextField
- tags: M2M → crm.Tag
- applications: M2M → JobPosting
- full_cv_transcript, self_summary, overall_knowledge: TextField
- distance_to_branches: TextField
- recommended_branch: CharField
- psicotest_score: FloatField
- embedding: VectorField (1536 dimensions)
- recruiter_summary: TextField
- recruiter_posting: IntegerField
- recruiter_status: CharField
- source: CharField
- distance_evaluation_done: BooleanField
- profile_picture: ImageField
- cv_file_doc: FK → RecruiterDocument
- code: UUIDField
- job_posting: FK → JobPosting
- tenant: FK → Tenant

Constraint: unique (document_id, tenant)

State transitions:
- discard(), hard_discard(), hire(), stand_by(), reject()
- preselect(), pending_data(), data_completed()
- invite_to_group_interview(), confirm_participation_group_interview()
- check_in(), no_show(), confirm_evaluation()
- individual_interview_stage(), interview()
- passed_group_evaluation(), failed_group_evaluation()
- unavailable(), no_response(), rejected(), request_data()

### CandidateList

- posting_id: IntegerField
- job_posting: FK → JobPosting
- candidate_document: CharField
- candidate: FK → Candidate
- status: CharField
- tenant: FK → Tenant

### RecruiterConfiguration

- company: FK → crm.Company
- hiringroom_*, psigma_*: Integration fields
- tenant: FK → Tenant

### Employee

- document_id: CharField
- hired: DateField
- branch, company, job: CharField
- status: CharField
- exit: DateField
- tenant: FK → Tenant

Constraint: unique (document_id, tenant)

### CandidateDistances

- candidate: FK → Candidate
- branch: FK → crm.Branch
- distance: FloatField
- distance_category: CharField
- duration: CharField
- duration_category: CharField
- tenant: FK → Tenant

### CandidateEvaluation

- candidate: FK → Candidate
- job_posting: FK → JobPosting
- comment: CharField
- overall_approve: BooleanField
- date: DateTimeField
- user: FK → User
- tenant: FK → Tenant

### CandidateEvaluationScore

- evaluation: FK → CandidateEvaluation
- topic, category, score: CharField

Constraint: unique (evaluation, category)

### CandidateInterviewNotes

- evaluation: FK → CandidateEvaluation
- date: DateTimeField
- note: TextField
- user: FK → User

### CandidateDraft

- fullname, email, phone, whatsapp: CharField
- date_birth: DateField
- address, city, state, postal_code: CharField
- document_id: CharField
- work_experience, education: TextField
- tags: M2M → crm.Tag
- full_cv_transcript, self_summary, overall_knowledge: TextField
- source: CharField
- profile_picture: ImageField
- cv_file_doc: FK → RecruiterDocument
- tenant: FK → Tenant

Class method: create_from_ocr()

## External Data Read

- crm.Contact
- crm.Branch
- crm.Company
- crm.Tag
- portal.Tenant
- portal.MoioUser
- portal.TenantConfiguration

## External Data Written

None directly.
