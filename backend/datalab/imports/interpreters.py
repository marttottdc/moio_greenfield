"""
LLM-based interpretation of PDF shape inspection results.
"""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ShapeInterpretationError(Exception):
    """Raised when shape interpretation fails."""


class ShapeInterpreter:
    """Interprets PDF shape inspection results using LLM."""

    def __init__(self, tenant_config: SimpleNamespace):
        """Initialize interpreter with tenant configuration."""
        self.tenant_config = tenant_config

    def interpret(self, shape_inspection: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpret shape inspection results using LLM.
        
        Args:
            shape_inspection: Shape inspection response containing fingerprint, description, etc.
        
        Returns:
            Interpretation with table descriptions, recommendations, and suggestions.
        """
        try:
            from moio_platform.lib.openai_gpt_api import full_chat_reply

            prompt = self._build_interpretation_prompt(shape_inspection)
            
            chat = [
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            response = full_chat_reply(
                chat=chat,
                openai_api_key=self.tenant_config.openai_api_key,
                model=self.tenant_config.openai_default_model
            )

            interpretation = json.loads(response)
            
            # Validate response structure
            return self._validate_interpretation(interpretation)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise ShapeInterpretationError(f"Invalid JSON response from LLM: {e}")
        except Exception as e:
            logger.error(f"Shape interpretation failed: {e}", exc_info=True)
            raise ShapeInterpretationError(f"Interpretation failed: {e}")

    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM interpretation."""
        return """You are a data analysis assistant specialized in interpreting PDF document structures.

Your task is to analyze PDF shape inspection results and provide clear, actionable insights about:
1. What each table likely represents (e.g., "invoice line items", "summary totals", "header information")
2. Which table(s) are most likely the main data tables vs. supporting information
3. Recommendations on which table(s) to extract for data import
4. Suggested column mappings based on column names
5. Overall document structure explanation (header pages, detail pages, footer pages)

You must respond with valid JSON following this exact structure:
{
    "summary": "Brief overall description of the document structure",
    "tables": [
        {
            "index": 0,
            "description": "What this table represents",
            "purpose": "main_data|summary|header|footer|other",
            "recommended": true|false,
            "reason": "Why this table is recommended or not",
            "column_analysis": {
                "suggested_types": {
                    "Date": "date",
                    "Amount": "decimal",
                    ...
                },
                "notes": "Any observations about column names or types"
            }
        },
        ...
    ],
    "recommendations": {
        "primary_table_index": 0,
        "additional_tables": [1, 2],
        "reasoning": "Why these tables are recommended",
        "warnings": ["Any potential issues or considerations"]
    },
    "structure_explanation": {
        "header_pages": "What appears on header pages",
        "detail_pages": "What appears on detail/repeating pages",
        "footer_pages": "What appears on footer pages",
        "pattern": "Overall pattern (e.g., 'Repeating invoice format')"
    }
}

Be concise but informative. Focus on actionable insights that help users decide which tables to extract."""

    def _build_interpretation_prompt(self, shape_inspection: Dict[str, Any]) -> str:
        """Build the user prompt from shape inspection data."""
        description = shape_inspection.get("description", {})
        fingerprint = shape_inspection.get("fingerprint", "")
        
        page_patterns = description.get("page_patterns", {})
        tables = description.get("tables", [])
        page_count = description.get("page_count", 0)
        warnings = description.get("warnings", [])
        
        prompt_parts = [
            "Analyze the following PDF shape inspection results:",
            "",
            f"Document Structure:",
            f"- Total pages: {page_count}",
            f"- Header pages: {page_patterns.get('header', [])}",
            f"- Detail pages: {page_patterns.get('detail', [])}",
            f"- Footer pages: {page_patterns.get('footer', [])}",
            "",
            f"Tables detected: {len(tables)}",
            ""
        ]
        
        for idx, table in enumerate(tables):
            page = table.get("page", "?")
            columns = table.get("columns", [])
            column_count = table.get("column_count", 0)
            row_estimate = table.get("row_count_estimate", 0)
            
            prompt_parts.append(
                f"Table {idx} (Page {page}):\n"
                f"- Columns ({column_count}): {', '.join(columns[:10])}"  # Limit to first 10 columns
                f"{'...' if len(columns) > 10 else ''}\n"
                f"- Estimated rows: {row_estimate}"
            )
            prompt_parts.append("")
        
        if warnings:
            prompt_parts.append(f"Warnings: {', '.join(warnings)}")
            prompt_parts.append("")
        
        prompt_parts.append(
            "Provide a detailed interpretation following the JSON structure specified in the system prompt."
        )
        
        return "\n".join(prompt_parts)

    def _validate_interpretation(self, interpretation: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize interpretation response."""
        # Ensure required fields exist
        if "summary" not in interpretation:
            interpretation["summary"] = "No summary provided"
        
        if "tables" not in interpretation:
            interpretation["tables"] = []
        
        if "recommendations" not in interpretation:
            interpretation["recommendations"] = {
                "primary_table_index": None,
                "additional_tables": [],
                "reasoning": "No recommendations available",
                "warnings": []
            }
        
        if "structure_explanation" not in interpretation:
            interpretation["structure_explanation"] = {
                "header_pages": "Unknown",
                "detail_pages": "Unknown",
                "footer_pages": "Unknown",
                "pattern": "Unknown"
            }
        
        # Ensure table indices match
        for idx, table in enumerate(interpretation.get("tables", [])):
            if "index" not in table:
                table["index"] = idx
        
        return interpretation
