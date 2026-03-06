---
title: "Assessments Error Handling"
slug: "assessments-errors"
category: "crm"
order: 6
status: "published"
summary: "- Wraps in `transaction.atomic()` for rollback safety - Returns `{'success': False, 'error': str, 'message': ...}` on exception - Creates response vectors for all questions atomically"
tags: ["assessments"]
---

## Overview

- Wraps in `transaction.atomic()` for rollback safety - Returns `{'success': False, 'error': str, 'message': ...}` on exception - Creates response vectors for all questions atomically

# assessments - Failures

## Explicit Error Handling

### AssessmentManager.initialize_assessment()
- Wraps in `transaction.atomic()` for rollback safety
- Returns `{'success': False, 'error': str, 'message': ...}` on exception
- Creates response vectors for all questions atomically

### AssessmentManager.handle_response()
- Validates request method (POST only)
- Returns `{'success': False, 'error': 'Invalid request method'}` for non-POST
- Catches `AssessmentInstanceResponseVector.DoesNotExist`
- Returns `{'success': False, 'error': 'Response vector not found'}` if vector missing
- Generic exception handler returns error message

### Response Validation Failures
- Missing mandatory response: `"This question requires a response"`
- Text too short: `"Response must be at least {min_length} characters"`
- Returns `{'success': False, 'errors': [...], 'message': 'Response validation failed'}`

### LLM Integration Failures
- If `llm_assistant` is None: `{'success': False, 'message': 'LLM not enabled for this campaign'}`
- LLM errors caught silently (insights appended only if available)

## Expected Failure Modes

### Database Failures
- Transaction rollback on any atomic block failure
- Response vector not found returns graceful error

### Validation Failures
- Invalid question type handling falls back to raw data storage
- Missing options for mandatory OPT questions returns validation error

### LLM Failures
- LLM processing failures logged but don't block assessment flow
- Insights generation failures return error response

## Recovery Mechanisms

- Atomic transactions ensure partial data not persisted
- Assessment can be resumed from last saved response vector
- Instance status preserved across failures
