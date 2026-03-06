"""
Document format schema definition.

Documents must follow this structure:
---
title: "Required title"
slug: "required-slug"
category: "valid-category-slug"
order: 10
status: draft | review | published
tags: [optional, tags]
requires_auth: true
api_endpoints: [operation_ids]  # Related API endpoints
---

# Content starts here

## Overview (required for guides)

## Prerequisites (optional)

## Steps / Content

## Next Steps (optional)
"""

# Required frontmatter fields
REQUIRED_FIELDS = {
    "title": str,
    "slug": str,
    "category": str,
}

# Optional frontmatter fields with defaults
OPTIONAL_FIELDS = {
    "order": (int, 0),
    "status": (str, "draft"),
    "summary": (str, ""),
    "tags": (list, []),
    "requires_auth": (bool, True),
    "api_endpoints": (list, []),
    "author": (str, ""),
    "updated_at": (str, ""),  # ISO date string
}

# Valid status values
VALID_STATUSES = ["draft", "review", "published"]

# Valid category slugs (must exist in GuideCategory)
VALID_CATEGORIES = [
    "getting-started",
    "crm",
    "campaigns",
    "flows",
    "chatbot",
    "datalab",
    "integrations",
    "api-reference",
    "tutorials",
    "best-practices",
]

# Document types and their required sections
DOCUMENT_TYPES = {
    "guide": {
        "required_sections": ["Overview"],
        "optional_sections": ["Prerequisites", "Steps", "Next Steps", "Related"],
    },
    "tutorial": {
        "required_sections": ["Overview", "Prerequisites", "Steps"],
        "optional_sections": ["Troubleshooting", "Next Steps"],
    },
    "reference": {
        "required_sections": [],
        "optional_sections": ["Parameters", "Response", "Examples", "Errors"],
    },
    "concept": {
        "required_sections": ["Overview"],
        "optional_sections": ["How It Works", "Best Practices", "Related"],
    },
}

# Content validation rules
CONTENT_RULES = {
    "min_length": 100,  # Minimum content length in characters
    "max_length": 50000,  # Maximum content length
    "require_code_blocks": False,  # At least one code block required
    "require_headings": True,  # Must have at least one heading
    "max_heading_depth": 4,  # Maximum heading level (h1-h4)
}

# File naming convention
FILE_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*\.md$"  # kebab-case.md
