"""
Pydantic-based ImportContract V1 schema for strong backend validation.
"""
from __future__ import annotations

from typing import List, Optional, Literal, Union

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    source: str
    target: str
    type: str
    clean: List[str] = Field(default_factory=list)
    format: Optional[str] = None


class PageSelector(BaseModel):
    kind: Literal["first", "last", "repeated", "regex"]
    value: Optional[str] = None


class StructuralUnit(BaseModel):
    kind: Literal["pdf_table", "pdf_region"]
    selector: PageSelector
    bbox: Optional[List[float]] = None


class ParserCSVExcel(BaseModel):
    type: Literal["csv", "excel"]
    delimiter: Optional[str] = None
    header_row: int
    skip_rows: int = 0
    range: Optional[dict] = None
    date_format: Optional[str] = None
    datetime_format: Optional[str] = None
    sheet: Optional[str] = None


class ParserPDF(BaseModel):
    type: Literal["pdf"]
    structural_unit: StructuralUnit
    date_format: Optional[str] = None
    datetime_format: Optional[str] = None


class ImportContractV1(BaseModel):
    version: Literal["1"] = "1"
    parser: Union[ParserCSVExcel, ParserPDF]
    mapping: List[ColumnMapping]

