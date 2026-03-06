"""
PDF shape inspection utilities for Data Lab.

Detects basic page patterns and table structures to produce a stable
shape fingerprint that can be used for compatibility checks.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from typing import Any, Dict, List

import fitz  # PyMuPDF
import pdfplumber

from datalab.core.serialization import serialize_for_json

logger = logging.getLogger(__name__)


class PDFShapeInspector:
    """Inspect a PDF and return a FileShape-like description."""

    def inspect(self, pdf_file: Any) -> Dict[str, Any]:
        """
        Inspect a PDF file-like object or path.

        Returns:
            {
                "fingerprint": "<hash>",
                "description": {
                    "page_patterns": {...},
                    "tables": [...],
                    "page_count": int,
                },
            }
        """
        pdf_bytes = self._read_bytes(pdf_file)

        page_patterns = self._detect_page_patterns(pdf_bytes)
        tables = self._extract_table_structures(pdf_bytes)
        page_count = page_patterns.get("page_count", 0)

        description = {
            "page_patterns": page_patterns,
            "tables": tables,
            "page_count": page_count,
        }

        fingerprint = self._fingerprint(description)

        return {
            "fingerprint": fingerprint,
            "description": description,
        }

    def _detect_page_patterns(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Identify simple header/detail/footer patterns.

        Heuristics:
        - header: first page
        - footer: last page (if more than 1 page)
        - detail: pages containing tables (from pdfplumber)
        """
        patterns: Dict[str, List[int]] = {"header": [], "detail": [], "footer": []}

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
            if page_count > 0:
                patterns["header"] = [0]
            if page_count > 1:
                patterns["footer"] = [page_count - 1]
            patterns["page_count"] = page_count

        # Detail pages = pages with tables
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for idx, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    if tables:
                        patterns["detail"].append(idx)
        except Exception as exc:
            logger.warning("Failed to detect detail pages via tables: %s", exc)

        return patterns

    def _extract_table_structures(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extract basic table structures from each page with sample data.

        Returns list of:
        {
            "page": int,
            "column_count": int,
            "columns": [col_name or index],
            "row_count_estimate": int,
            "sample_rows": [{"col1": val1, "col2": val2, ...}, ...]  # First 10 rows
        }
        """
        tables_summary: List[Dict[str, Any]] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for idx, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    for table_idx, tbl in enumerate(tables):
                        if not tbl or len(tbl) == 0:
                            continue
                        
                        # First row is header
                        header = tbl[0] if tbl else []
                        columns = [col if col else f"col_{i}" for i, col in enumerate(header)]
                        
                        # Extract sample rows (first 10 data rows, excluding header)
                        sample_rows = []
                        data_rows = tbl[1:] if len(tbl) > 1 else []
                        for row in data_rows[:10]:  # Limit to first 10 rows
                            # Pad row if needed, or truncate if too long
                            padded_row = row + [None] * (len(columns) - len(row))
                            row_dict = {
                                columns[i]: serialize_for_json(padded_row[i]) 
                                for i in range(len(columns))
                            }
                            sample_rows.append(row_dict)
                        
                        row_count = max(len(tbl) - 1, 0)
                        tables_summary.append(
                            {
                                "page": idx,
                                "table_index": table_idx,  # Index of table on this page
                                "column_count": len(columns),
                                "columns": columns,
                                "row_count_estimate": row_count,
                                "sample_rows": sample_rows,  # Actual sample data
                            }
                        )
        except Exception as exc:
            logger.warning("Failed to extract table structures: %s", exc)

        return tables_summary

    def _fingerprint(self, description: Dict[str, Any]) -> str:
        """
        Create a stable fingerprint from description, excluding page_count.
        
        Page count is excluded because files can have different amounts of data
        while replicating the same structure. This ensures the fingerprint remains
        stable across files with identical structure but varying data volumes.
        """
        # Create a copy to avoid modifying the original
        fingerprint_data = description.copy()
        
        # Remove page_count from top level
        fingerprint_data.pop("page_count", None)
        
        # Remove page_count from page_patterns if present
        if "page_patterns" in fingerprint_data:
            page_patterns = fingerprint_data["page_patterns"].copy()
            page_patterns.pop("page_count", None)
            fingerprint_data["page_patterns"] = page_patterns
        
        # Remove row_count_estimate and sample_rows from tables (data volume, not structure)
        if "tables" in fingerprint_data:
            tables = fingerprint_data["tables"]
            fingerprint_data["tables"] = [
                {k: v for k, v in table.items() if k not in ("row_count_estimate", "sample_rows", "table_index")}
                for table in tables
            ]
        
        serialized = json.dumps(fingerprint_data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _read_bytes(self, pdf_file: Any) -> bytes:
        """Read file-like or path into bytes."""
        if isinstance(pdf_file, (str, bytes, bytearray)):
            if isinstance(pdf_file, str):
                with open(pdf_file, "rb") as f:
                    return f.read()
            return bytes(pdf_file)

        # File-like
        data = pdf_file.read()
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
        return data
