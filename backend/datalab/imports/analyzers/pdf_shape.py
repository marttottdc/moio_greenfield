"""
PDF Shape Analyzer

Provides a formal interface to inspect PDF files and return a stable
shape fingerprint plus structural diagnostics.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from typing import Any, Dict, List

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)


class PdfShapeAnalyzerError(Exception):
    """Raised when PDF shape analysis fails."""


class PdfShapeAnalyzer:
    """Analyze PDF structure to produce shape fingerprint and details."""

    def analyze(self, file_path_or_obj: Any) -> Dict[str, Any]:
        """
        Analyze a PDF and return shape information.

        Returns:
            {
                "fingerprint": "<sha256>",
                "page_patterns": {"header": [...], "detail": [...], "footer": [...], "page_count": int},
                "tables": [
                    {"page": int, "column_count": int, "columns": [...], "row_count_estimate": int}
                ],
                "warnings": []
            }
        """
        try:
            pdf_bytes = self._read_bytes(file_path_or_obj)
            page_patterns = self._detect_page_patterns(pdf_bytes)
            tables = self._extract_tables(pdf_bytes)

            description = {
                "page_patterns": page_patterns,
                "tables": tables,
                "page_count": page_patterns.get("page_count", 0),
                "warnings": [],
            }

            fingerprint = self._fingerprint(description)
            return {"fingerprint": fingerprint, "description": description}
        except Exception as e:
            logger.error(f"PDF shape analysis failed: {e}", exc_info=True)
            raise PdfShapeAnalyzerError(str(e))

    def _read_bytes(self, file_path_or_obj: Any) -> bytes:
        if isinstance(file_path_or_obj, (str, bytes, bytearray)):
            if isinstance(file_path_or_obj, str):
                with open(file_path_or_obj, "rb") as f:
                    return f.read()
            return bytes(file_path_or_obj)

        data = file_path_or_obj.read()
        if hasattr(file_path_or_obj, "seek"):
            file_path_or_obj.seek(0)
        return data

    def _detect_page_patterns(self, pdf_bytes: bytes) -> Dict[str, Any]:
        patterns = {"header": [], "detail": [], "footer": []}
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
            if page_count > 0:
                patterns["header"] = [0]
            if page_count > 1:
                patterns["footer"] = [page_count - 1]
            patterns["page_count"] = page_count

        # Detect detail pages via tables
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for idx, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    if tables:
                        patterns["detail"].append(idx)
        except Exception as e:
            logger.warning(f"Failed to detect detail pages: {e}")

        return patterns

    def _extract_tables(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for idx, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    for tbl in tables:
                        if not tbl:
                            continue
                        header = tbl[0] if tbl else []
                        columns = [col if col else f"col_{i}" for i, col in enumerate(header)]
                        row_count = max(len(tbl) - 1, 0)
                        results.append(
                            {
                                "page": idx,
                                "column_count": len(columns),
                                "columns": columns,
                                "row_count_estimate": row_count,
                            }
                        )
        except Exception as e:
            logger.warning(f"Failed to extract tables: {e}")
        return results

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
        
        # Remove row_count_estimate from tables (data volume, not structure)
        if "tables" in fingerprint_data:
            tables = fingerprint_data["tables"]
            fingerprint_data["tables"] = [
                {k: v for k, v in table.items() if k != "row_count_estimate"}
                for table in tables
            ]
        
        # Remove warnings (not part of structural identity)
        fingerprint_data.pop("warnings", None)
        
        serialized = json.dumps(fingerprint_data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
