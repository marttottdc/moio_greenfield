---
title: "Assessments Lifecycle"
slug: "assessments-lifecycle"
category: "crm"
order: 3
status: "published"
summary: "- Imports signals module on app ready (`assessments.signals`)"
tags: ["assessments"]
---

## Overview

- Imports signals module on app ready (`assessments.signals`)

# assessments - Lifecycle

## Startup Behavior

- Imports signals module on app ready (`assessments.signals`)

## Runtime Behavior

### Assessment Instance State Machine

```
NEW (N)
  │
  ├── initialize_assessment()
  │
  ▼
QUESTIONS_LOOP (Q) ◄────────┐
  │                         │
  ├── handle_response()     │
  │   └── _validate_response()
  │   └── _update_progress()
  │   └── LLM process_response() (if enabled)
  │                         │
  ├── more questions? ──────┘
  │
  ├── all answered
  │
  ▼
READY (R)
  │
  ├── generate_insights() (if LLM enabled)
  │
  ▼
COMPLETED (C)
```

### Question Sequencing Flow

1. `get_next_question()` called
2. `_apply_conditional_logic()` evaluates rules from completed responses
3. For each rule matching current state:
   - `skip_to`: Jump to specific question
   - `skip_questions`: Mark questions as skipped
4. If no conditional match, return next planned unanswered question
5. Return `None` when no more questions

### Response Processing

1. Validate request method (POST only)
2. Retrieve response vector by ID
3. Validate response based on question type:
   - **OPT**: Extract selected options with values
   - **SHI/LOI**: Validate text against min_length rules
   - **Other**: Store raw POST data
4. Mark response as done, valid
5. Update instance progress counters
6. If LLM enabled, process response for insights
7. Determine and return next question

### Progress Tracking

- `answered_questions`: Count of responses with `done=True`
- `total_questions`: Set during initialization
- `progress_percentage`: Calculated as `(answered / total) * 100`
- Auto-completion when `answered >= total`

## Shutdown Behavior

No explicit shutdown behavior defined.
