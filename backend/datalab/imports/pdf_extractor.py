"""
PDF extraction utilities for Data Lab StructuralUnits.

Supports:
- Page selection (first, last, repeated, regex)
- Table extraction via pdfplumber
- Region text extraction via PyMuPDF
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, List

import fitz  # PyMuPDF
import pandas as pd
import pdfplumber

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails."""


class PDFExtractor:
    """Extract data from PDF according to a StructuralUnit-like selector."""

    def extract_pdf_as_json(self, pdf_file: Any, structural_unit: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """
        Extract full PDF structure as a JSON-friendly object using pdfplumber.

        Args:
            pdf_file: PDF file-like object or path.
            structural_unit: Optional structural unit with page selector and bbox to limit extraction.

        Returns:
            {
                "pages": [
                    {
                        "page_number": int,
                        "tables": [...],  # list of tables, each table is list[list[Any]]
                        "text": str,
                        "words": [...],   # list of word dicts with bounding boxes
                        "chars": [...],   # list of char dicts with positions
                        "lines": [...],   # list of line dicts
                    }
                ],
                "metadata": {
                    "page_count": int,
                    "extraction_method": "pdfplumber"
                }
            }
        """
        try:
            pdf_bytes = self._read_bytes(pdf_file)
            selector = (structural_unit or {}).get("selector", {}) if structural_unit else {}
            page_selector = selector.get("page_selector", {"type": "first"}) if structural_unit else {"type": "first"}
            bbox = selector.get("bbox") if structural_unit else None

            pages = self._select_pages(pdf_bytes, page_selector) if structural_unit else None

            pages_data: List[Dict[str, Any]] = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                page_indices = pages if pages is not None else list(range(len(pdf.pages)))
                for idx in page_indices:
                    if idx >= len(pdf.pages):
                        continue
                    page = pdf.pages[idx]
                    target_page = page.crop(bbox) if bbox else page

                    tables = target_page.extract_tables() or []
                    text = target_page.extract_text() or ""
                    words = target_page.extract_words() or []
                    chars = getattr(target_page, "chars", []) or []
                    lines = getattr(target_page, "lines", []) or []

                    pages_data.append(
                        {
                            "page_number": idx,
                            "tables": tables,
                            "text": text,
                            "words": words,
                            "chars": chars,
                            "lines": lines,
                        }
                    )

            return {
                "pages": pages_data,
                "metadata": {
                    "page_count": len(pages_data),
                    "extraction_method": "pdfplumber",
                },
            }
        except Exception as exc:
            raise PDFExtractionError(f"Failed to extract PDF as JSON: {exc}") from exc

    def extract_structural_unit(self, pdf_file: Any, structural_unit: Dict[str, Any]) -> pd.DataFrame:
        """
        Extract data for a structural unit.

        structural_unit:
        {
            "kind": "pdf_table" | "pdf_region",
            "selector": {
                "page_selector": {"type": "first|last|repeated|regex", "value": optional},
                "bbox": [x1, y1, x2, y2]
            }
        }
        """
        try:
            pdf_bytes = self._read_bytes(pdf_file)
            selector = structural_unit.get("selector", {})
            page_selector = selector.get("page_selector", {"type": "first"})
            bbox = selector.get("bbox")
            if not bbox or len(bbox) != 4:
                raise PDFExtractionError("selector.bbox is required with four coordinates [x1, y1, x2, y2]")

            pages = self._select_pages(pdf_bytes, page_selector)

            if structural_unit.get("kind") == "pdf_table":
                return self._extract_tables(pdf_bytes, pages, bbox)
            elif structural_unit.get("kind") == "pdf_region":
                return self._extract_region_text(pdf_bytes, pages, bbox)
            else:
                raise PDFExtractionError(f"Unsupported structural unit kind: {structural_unit.get('kind')}")
        except Exception as exc:
            logger.error("Failed to extract structural unit: %s", exc, exc_info=True)
            raise

    def _select_pages(self, pdf_bytes: bytes, selector: Dict[str, Any]) -> List[int]:
        """Select pages based on selector."""
        selector_type = selector.get("type", "first")
        value = selector.get("value")

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
            if page_count == 0:
                return []

            if selector_type == "first":
                return [0]
            if selector_type == "last":
                return [page_count - 1]
            if selector_type == "repeated":
                # Heuristic: treat all pages except header/footer as repeated detail pages
                if page_count <= 2:
                    return list(range(page_count))
                return list(range(1, page_count - 1))
            if selector_type == "regex":
                if not value:
                    raise PDFExtractionError("regex selector requires 'value'")
                pattern = re.compile(value, re.IGNORECASE)
                matches: List[int] = []
                for idx in range(page_count):
                    page = doc.load_page(idx)
                    text = page.get_text("text") or ""
                    if pattern.search(text):
                        matches.append(idx)
                return matches

            raise PDFExtractionError(f"Unknown page_selector type: {selector_type}")

    def _extract_tables(self, pdf_bytes: bytes, pages: List[int], bbox: List[float]) -> pd.DataFrame:
        """Extract tables from selected pages using pdfplumber."""
        rows: List[List[Any]] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for idx in pages:
                    if idx >= len(pdf.pages):
                        continue
                    page = pdf.pages[idx]
                    cropped = page.crop(bbox)
                    tables = cropped.extract_tables()
                    for tbl in tables:
                        rows.extend(tbl)
        except Exception as exc:
            raise PDFExtractionError(f"Failed to extract tables: {exc}") from exc

        if not rows:
            return pd.DataFrame()

        # Assume first row is header
        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        columns = [col if col else f"col_{i}" for i, col in enumerate(header)]
        return pd.DataFrame(data_rows, columns=columns)

    def _extract_region_text(self, pdf_bytes: bytes, pages: List[int], bbox: List[float]) -> pd.DataFrame:
        """Extract text from region using PyMuPDF; return DataFrame with a single column 'text'."""
        texts: List[str] = []
        rect = fitz.Rect(*bbox)
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for idx in pages:
                if idx >= len(doc):
                    continue
                page = doc.load_page(idx)
                text = page.get_text("text", clip=rect) or ""
                if text:
                    texts.append(text.strip())

        return pd.DataFrame({"text": texts})

    def _read_bytes(self, pdf_file: Any) -> bytes:
        """Read file-like or path into bytes."""
        if isinstance(pdf_file, (str, bytes, bytearray)):
            if isinstance(pdf_file, str):
                with open(pdf_file, "rb") as f:
                    return f.read()
            return bytes(pdf_file)

        data = pdf_file.read()
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
        return data
