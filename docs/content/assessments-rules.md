---
title: "Assessments Rules & Constraints"
slug: "assessments-rules"
category: "crm"
order: 5
status: "published"
summary: "- Campaign must have `tenant` (tenant-scoped) - Campaign name unique per tenant (implicit from TenantScopedModel) - `llm_enabled` flag controls LLM integration availability"
tags: ["assessments"]
---

## Overview

- Campaign must have `tenant` (tenant-scoped) - Campaign name unique per tenant (implicit from TenantScopedModel) - `llm_enabled` flag controls LLM integration availability

# assessments - Invariants

## Data Integrity Rules

### Campaign Rules
- Campaign must have `tenant` (tenant-scoped)
- Campaign name unique per tenant (implicit from TenantScopedModel)
- `llm_enabled` flag controls LLM integration availability

### Question Rules
- Questions belong to exactly one campaign
- Questions have unique order within a campaign
- Question type must be one of: WEL, IWO, SHI, LOI, OPT, CON, DAT, SCA, MUL
- `validation_rules` JSON must match question type requirements

### Response Vector Rules
- One response vector per question per instance
- `mandatory` derived from `not question.optional` during initialization
- Once `done=True`, response is considered final
- `planned=True` indicates question is in sequence, `False` if skipped

### Instance Rules
- Instance belongs to exactly one campaign and optionally one contact
- Status transitions are unidirectional (cannot go back to previous state)
- `completed_at` only set when status transitions to COMPLETED
- `answered_questions` must never exceed `total_questions`

## Validation Constraints

### Text Input Validation
- `min_length` rule enforced for SHI/LOI types
- Empty responses rejected if `mandatory=True`

### Option Validation
- At least one option required if `mandatory=True` for OPT type
- Selected options must exist in question's options queryset

### Conditional Logic Validation
- `condition_type` must be one of: option_selected, text_contains, value_greater_than
- `skip_to` requires valid `target_question_id`
- `skip_questions` requires non-empty `question_ids` list
