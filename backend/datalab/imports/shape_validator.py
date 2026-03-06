"""
Shape validation utilities for PDF imports.

Validates detected shapes against expected patterns (header/detail/footer)
and required table presence.
"""
from __future__ import annotations

from typing import Any, Dict, List


class ShapeValidationResult(Dict[str, Any]):
    """Simple dict alias for validation result."""


class ShapeValidator:
    """Validate detected PDF shapes."""

    def validate_pdf_shape(self, detected: Dict[str, Any], expected_shape: Dict[str, Any]) -> ShapeValidationResult:
        """
        Validate PDF shape patterns.

        Returns:
            {
                "status": "pass" | "fail" | "partial",
                "score": float,
                "reasons": [str, ...],
            }
        """
        reasons: List[str] = []
        score = 1.0

        # Page pattern validation
        expected_patterns = expected_shape.get("page_patterns", {})
        detected_patterns = (detected or {}).get("page_patterns", {})
        page_pattern_result = self.validate_page_patterns(detected_patterns, expected_patterns)
        reasons.extend(page_pattern_result["reasons"])
        score *= page_pattern_result["score"]

        # Table presence validation (if provided)
        required_tables = expected_shape.get("required_tables", [])
        if required_tables:
            tables = (detected or {}).get("tables", [])
            for requirement in required_tables:
                page = requirement.get("page")
                min_columns = requirement.get("min_columns", 1)
                found = any(
                    t.get("page") == page and t.get("column_count", 0) >= min_columns
                    for t in tables
                )
                if not found:
                    reasons.append(
                        f"Required table not found on page {page} with at least {min_columns} columns"
                    )
                    score *= 0.5

        status = "pass" if not reasons else ("partial" if score >= 0.5 else "fail")

        return {
            "status": status,
            "score": round(score, 3),
            "reasons": reasons,
        }

    def validate_page_patterns(
        self,
        detected: Dict[str, Any],
        expected: Dict[str, Any],
    ) -> ShapeValidationResult:
        """Validate header/detail/footer patterns."""
        reasons: List[str] = []
        score = 1.0

        for pattern_key, expectation in expected.items():
            if pattern_key == "page_count":
                continue

            detected_pages = detected.get(pattern_key, [])
            rule = expectation

            if rule == "exactly_one":
                if len(detected_pages) != 1:
                    reasons.append(f"{pattern_key}: expected exactly_one, found {len(detected_pages)}")
                    score *= 0.5
            elif rule == "one_or_more":
                if len(detected_pages) < 1:
                    reasons.append(f"{pattern_key}: expected one_or_more, found none")
                    score *= 0.5
            elif rule == "zero_or_one":
                if len(detected_pages) > 1:
                    reasons.append(f"{pattern_key}: expected zero_or_one, found {len(detected_pages)}")
                    score *= 0.5

        return {"status": "pass" if not reasons else "partial", "score": score, "reasons": reasons}
