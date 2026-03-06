---
title: "Assessments API"
slug: "assessments-api"
category: "crm"
order: 2
status: "published"
summary: "No public API endpoints exposed (internal use only via AssessmentManager)."
tags: ["assessments"]
---

## Overview

No public API endpoints exposed (internal use only via AssessmentManager).

# assessments - Interfaces

## Public Endpoints

No public API endpoints exposed (internal use only via AssessmentManager).

## Internal API

### AssessmentManager

```python
class AssessmentManager:
    def __init__(self, assessment_instance: AssessmentInstance)
    def initialize_assessment(self) -> Dict[str, Any]
    def handle_response(self, request) -> Dict[str, Any]
    def get_next_step(self) -> Optional[Dict[str, Any]]
    def generate_insights(self) -> Dict[str, Any]
    def get_results(self) -> Dict[str, Any]
```

### AssessmentFlowEngine

```python
class AssessmentFlowEngine:
    def __init__(self, assessment_instance: AssessmentInstance)
    def get_next_question(self) -> Optional[Dict[str, Any]]
    def calculate_progress(self) -> Dict[str, Any]
    def get_assessment_summary(self) -> Dict[str, Any]
```

## Events Emitted

None explicitly visible in code.

## Events Consumed

None explicitly visible in code.

## Input/Output Schemas

### Question Types

| Code | Name | Description |
|------|------|-------------|
| WEL | Welcome | Welcome screen |
| IWO | Input With Options | Text input with preset options |
| SHI | Short Input | Short text input |
| LOI | Long Input | Long text input (textarea) |
| OPT | Options | Single/multi select options |
| CON | Contact Data | Contact information collection |
| DAT | Date Data | Date picker |
| SCA | Scale Rating | Numeric scale (e.g., 1-10) |
| MUL | Multiple Choice | Multiple selection |

### Campaign Types

| Code | Name | Description |
|------|------|-------------|
| FORM | Form | Generic form |
| DIAG | Diagnostic | Diagnostic assessment |
| SURV | Survey | Survey collection |
| QUIZ | Quiz | Quiz with scoring |

### Instance Status Flow

| Code | Name | Description |
|------|------|-------------|
| N | New | Instance created |
| Q | Questions Loop | Actively answering questions |
| S1 | S1 Planned | Scheduled phase |
| R | Ready | Ready for completion |
| C | Completed | All questions answered |
| X | Cancelled | Instance cancelled |

### Response Vector Output

```python
{
    "response_vector_id": str,
    "question_id": str,
    "question": str,
    "description": str,
    "type": str,  # Question type code
    "configuration": dict,
    "optional": bool,
    "image": str | None,
    "options": [
        {
            "id": str,
            "option": str,
            "meaning": str,
            "value": float,
            "image": str | None
        }
    ],
    "validation_rules": dict,
    "topic": str
}
```

### Conditional Logic Schema

```python
{
    "rules": [
        {
            "condition_type": "option_selected" | "text_contains" | "value_greater_than",
            "condition_value": str | int,
            "action": "skip_to" | "skip_questions",
            "target_question_id": str,  # For skip_to
            "question_ids": [str]  # For skip_questions
        }
    ]
}
```

### Results Output

```python
{
    "instance_id": str,
    "campaign": str,
    "status": str,
    "progress": float,
    "total_questions": int,
    "answered_questions": int,
    "created_at": datetime,
    "completed_at": datetime | None,
    "responses": [
        {
            "question": str,
            "type": str,
            "response": dict,
            "created_at": datetime
        }
    ],
    "insights": str,
    "score": float | None
}
```
