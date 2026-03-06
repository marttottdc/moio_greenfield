"""
File parsers for Data Lab.

Supports CSV and Excel file parsing with configurable options.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from datalab.imports.pdf_extractor import PDFExtractor, PDFExtractionError

logger = logging.getLogger(__name__)


class FileParserError(Exception):
    """Raised when file parsing fails."""
    pass


class FileParser:
    """Parser for CSV, Excel, and PDF files."""
    
    @staticmethod
    def parse_csv(
        file_obj: Any,
        header_row: int = 0,
        skip_rows: int = 0,
        range_config: dict | None = None,
        delimiter: str = ',',
        encoding: str | None = 'utf-8'
    ) -> pd.DataFrame:
        """
        Parse CSV file into DataFrame.
        
        Args:
            file_obj: File-like object or path to CSV file
            header_row: 0-based index of header row (default: 0)
            skip_rows: Number of rows to skip before header (default: 0)
            range_config: Optional dict with 'start_row', 'end_row' (0-based)
            delimiter: CSV delimiter character (default: ',')
            encoding: Preferred encoding (default: 'utf-8'). Falls back to latin-1/cp1252 on error.
            
        Returns:
            DataFrame with parsed data
            
        Raises:
            FileParserError: If parsing fails
        """
        import io
        
        # Read raw bytes first to handle encoding ourselves
        try:
            file_obj.seek(0)
            raw_bytes = file_obj.read()
            if isinstance(raw_bytes, str):
                # Already decoded, use as-is
                raw_bytes = raw_bytes.encode('utf-8')
        except Exception as e:
            raise FileParserError(f"Failed to read file: {e}") from e
        
        # Build encoding fallback list
        encodings_to_try = []
        if encoding:
            encodings_to_try.append(encoding)
        for fallback in ['utf-8', 'latin-1', 'cp1252']:
            if fallback not in encodings_to_try:
                encodings_to_try.append(fallback)
        
        # Try to decode with each encoding
        decoded_content = None
        used_encoding = None
        last_decode_err = None
        for enc in encodings_to_try:
            try:
                decoded_content = raw_bytes.decode(enc)
                used_encoding = enc
                break
            except (UnicodeDecodeError, LookupError) as e:
                last_decode_err = e
                logger.debug(f"CSV decode failed with {enc}: {e}")
                continue
        
        if decoded_content is None:
            raise FileParserError(f"CSV parsing failed: could not decode with any encoding ({', '.join(encodings_to_try)}). Last error: {last_decode_err}")
        
        if used_encoding != encoding:
            logger.info(f"CSV decoded using fallback encoding: {used_encoding}")
        
        # Calculate skiprows: header_row includes the skipped rows
        skiprows = list(range(skip_rows))
        if header_row > skip_rows:
            skiprows.extend(range(skip_rows + 1, header_row))
        
        try:
            df = pd.read_csv(
                io.StringIO(decoded_content),
                header=header_row - skip_rows if header_row >= skip_rows else header_row,
                skiprows=skiprows if skiprows else None,
                dtype=str,  # Read everything as string initially, type casting happens later
                keep_default_na=False,  # Don't convert empty strings to NaN
                on_bad_lines='skip',  # Skip bad lines instead of failing
                sep=delimiter  # Use specified delimiter
            )
        except Exception as e:
            logger.error(f"Failed to parse CSV: {e}")
            raise FileParserError(f"CSV parsing failed: {e}") from e

        # Apply range if specified
        if range_config:
            start_row = range_config.get('start_row', 0)
            end_row = range_config.get('end_row')
            if end_row is not None:
                df = df.iloc[start_row:end_row]
            else:
                df = df.iloc[start_row:]
        
        logger.info(f"Parsed CSV: {len(df)} rows, {len(df.columns)} columns")
        return df
    
    @staticmethod
    def parse_excel(
        file_obj: Any,
        sheet: str | int = 0,
        header_row: int = 0,
        skip_rows: int = 0,
        range_config: dict | None = None
    ) -> pd.DataFrame:
        """
        Parse Excel file into DataFrame.
        
        Args:
            file_obj: File-like object or path to Excel file
            sheet: Sheet name or 0-based index (default: 0)
            header_row: 0-based index of header row (default: 0)
            skip_rows: Number of rows to skip before header (default: 0)
            range_config: Optional dict with 'start_row', 'end_row', 'start_col', 'end_col'
            
        Returns:
            DataFrame with parsed data
            
        Raises:
            FileParserError: If parsing fails
        """
        try:
            # Calculate skiprows similar to CSV
            skiprows = list(range(skip_rows))
            if header_row > skip_rows:
                skiprows.extend(range(skip_rows + 1, header_row))
            
            # Read Excel
            df = pd.read_excel(
                file_obj,
                sheet_name=sheet,
                header=header_row - skip_rows if header_row >= skip_rows else header_row,
                skiprows=skiprows if skiprows else None,
                dtype=str,  # Read everything as string initially
                keep_default_na=False,
                engine='openpyxl'
            )
            
            # Apply range if specified
            if range_config:
                start_row = range_config.get('start_row', 0)
                end_row = range_config.get('end_row')
                start_col = range_config.get('start_col')
                end_col = range_config.get('end_col')
                
                # Convert column letters to indices if needed
                if start_col is not None and isinstance(start_col, str):
                    start_col = FileParser._column_letter_to_index(start_col)
                if end_col is not None and isinstance(end_col, str):
                    end_col = FileParser._column_letter_to_index(end_col) + 1
                
                # Apply row range
                if end_row is not None:
                    df = df.iloc[start_row:end_row]
                else:
                    df = df.iloc[start_row:]
                
                # Apply column range
                if start_col is not None or end_col is not None:
                    df = df.iloc[:, start_col:end_col]
            
            logger.info(f"Parsed Excel sheet '{sheet}': {len(df)} rows, {len(df.columns)} columns")
            return df
            
        except Exception as e:
            logger.error(f"Failed to parse Excel: {e}")
            raise FileParserError(f"Excel parsing failed: {str(e)}") from e

    @staticmethod
    def parse_pdf(
        file_obj: Any,
        structural_unit: dict | None = None
    ) -> pd.DataFrame:
        """
        Parse PDF file into DataFrame using a StructuralUnit selector.

        Args:
            file_obj: File-like object or path to PDF
            structural_unit: {
                "kind": "pdf_table" | "pdf_region",
                "selector": {
                    "page_selector": {"type": "first|last|repeated|regex", "value": optional},
                    "bbox": [x1, y1, x2, y2]
                }
            }
        """
        if structural_unit is None:
            raise FileParserError("structural_unit is required for PDF parsing")

        extractor = PDFExtractor()
        try:
            df = extractor.extract_structural_unit(file_obj, structural_unit)
            logger.info(f"Parsed PDF structural unit: {len(df)} rows, {len(df.columns)} columns")
            return df
        except PDFExtractionError as e:
            logger.error(f"Failed to parse PDF: {e}")
            raise FileParserError(f"PDF parsing failed: {str(e)}") from e
    
    @staticmethod
    def detect_schema(df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Auto-detect schema (column types) from DataFrame.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            List of column definitions: [{'name': 'col', 'type': 'string', 'nullable': bool}, ...]
        """
        schema = []
        
        for col in df.columns:
            col_data = df[col]
            
            # Detect type
            dtype = col_data.dtype
            
            if pd.api.types.is_integer_dtype(dtype):
                detected_type = 'integer'
            elif pd.api.types.is_float_dtype(dtype):
                detected_type = 'decimal'
            elif pd.api.types.is_bool_dtype(dtype):
                detected_type = 'boolean'
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                detected_type = 'date'
            else:
                # Try to detect date strings
                if col_data.dtype == 'object':
                    # Sample non-null values to check for dates
                    sample = col_data.dropna().head(100)
                    if len(sample) > 0:
                        try:
                            pd.to_datetime(sample, errors='raise')
                            detected_type = 'date'
                        except (ValueError, TypeError):
                            detected_type = 'string'
                    else:
                        detected_type = 'string'
                else:
                    detected_type = 'string'
            
            # Check nullable
            nullable = col_data.isna().any() if hasattr(col_data, 'isna') else False
            
            schema.append({
                'name': str(col),
                'type': detected_type,
                'nullable': bool(nullable)
            })
        
        return schema
    
    @staticmethod
    def _column_letter_to_index(letter: str) -> int:
        """
        Convert Excel column letter to 0-based index.
        
        Args:
            letter: Column letter (e.g., 'A', 'Z', 'AA')
            
        Returns:
            0-based column index
        """
        result = 0
        for char in letter.upper():
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result - 1
