---
title: "Assessments Overview"
slug: "assessments-overview"
category: "crm"
order: 1
status: "published"
summary: "Survey, quiz, and form assessment engine for collecting structured responses from users with LLM integration for insights generation."
tags: ["assessments"]
---

## Overview

Survey, quiz, and form assessment engine for collecting structured responses from users with LLM integration for insights generation.

# assessments

## Responsibility

Survey, quiz, and form assessment engine for collecting structured responses from users with LLM integration for insights generation.

## What it Owns

- **Campaign**: Assessment campaign definitions (forms, diagnostics, surveys, quizzes) with LLM enablement flag
- **AssessmentQuestion**: Questions with multiple types, validation rules, conditional logic, ordering
- **AssessmentQuestionOption**: Answer options with values, meanings, and optional images
- **AssessmentInstance**: User progress tracking through an assessment
- **AssessmentInstanceResponseVector**: Individual response storage per question per instance
- **PainPoint**: Pain point definitions for diagnostic assessments

## Core Components

### AssessmentManager (`core/assessment_manager.py`)
Orchestrates assessment lifecycle:
- `initialize_assessment()`: Creates response vectors for all questions, sets instance status
- `handle_response()`: Validates and processes user responses with LLM integration
- `get_next_step()`: Delegates to flow engine for next question
- `generate_insights()`: LLM-based final insights generation
- `get_results()`: Returns complete assessment results and analytics

### AssessmentFlowEngine (`core/flow_engine.py`)
Handles question sequencing and conditional logic:
- `get_next_question()`: Determines next question based on conditional rules
- `_apply_conditional_logic()`: Evaluates skip/branch rules based on responses
- `_evaluate_condition()`: Supports option_selected, text_contains, value_greater_than conditions
- `calculate_progress()`: Returns progress percentage and remaining questions

### LLMAssessmentAssistant (`core/llm_assistant.py`)
LLM integration for enhanced assessments:
- `process_response()`: Generates insights per response
- `generate_final_insights()`: Creates summary insights after completion

## What it Does NOT Do

- Does not handle user authentication (delegates to portal)
- Does not manage contacts (delegates to crm)
- Does not send notifications directly (delegates to chatbot/campaigns)
- Does not persist chat sessions (delegates to chatbot)
