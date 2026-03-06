---
title: "Assessments Data Model"
slug: "assessments-data"
category: "crm"
order: 4
status: "published"
summary: "- id: UUID (PK) - name: CharField (unique per tenant) - description: TextField - tenant: FK → Tenant - active: BooleanField - public: BooleanField - type: CharField (FORM, DIAG, SURV, QUIZ) - llm_enab"
tags: ["assessments"]
---

## Overview

- id: UUID (PK) - name: CharField (unique per tenant) - description: TextField - tenant: FK → Tenant - active: BooleanField - public: BooleanField - type: CharField (FORM, DIAG, SURV, QUIZ) - llm_enab

# assessments - Data

## Owned Data Models

### AssessmentCampaign

- id: UUID (PK)
- name: CharField (unique per tenant)
- description: TextField
- tenant: FK → Tenant
- active: BooleanField
- public: BooleanField
- type: CharField (FORM, DIAG, SURV, QUIZ)
- llm_enabled: BooleanField
- llm_assistant_prompt: TextField
- llm_content_generation: BooleanField
- llm_flow_management: BooleanField
- created_at, updated_at: DateTimeField

### AssessmentQuestion

- id: UUID (PK)
- question: CharField
- type: CharField (question types)
- configuration: JSONField
- question_group: IntegerField
- optional: BooleanField
- order: IntegerField
- campaign: FK → AssessmentCampaign
- topic: CharField
- image: ImageField
- validation_rules: JSONField
- conditional_logic: JSONField
- description: TextField

### AssessmentQuestionOption

- id: UUID (PK)
- question: FK → AssessmentQuestion
- option: CharField
- meaning: CharField
- image: ImageField
- order: IntegerField
- value: IntegerField (for scoring)

### AssessmentInstance

- id: UUID (PK)
- status: CharField
- step: IntegerField
- campaign: FK → AssessmentCampaign
- user: FK → User
- total_questions: IntegerField
- answered_questions: IntegerField
- score: JSONField
- insights: TextField
- completed_at: DateTimeField

### AssessmentInstanceResponseVector

- id: UUID (PK)
- instance: FK → AssessmentInstance
- question: FK → AssessmentQuestion
- planned: BooleanField
- mandatory: BooleanField
- done: BooleanField
- response: JSONField
- is_valid: BooleanField
- validation_errors: JSONField

### PainPoint

- id: UUID (PK)
- name: CharField (unique)
- description: TextField
- tenant: FK → Tenant

## External Data Read

- portal.Tenant
- portal.MoioUser

## External Data Written

None.
