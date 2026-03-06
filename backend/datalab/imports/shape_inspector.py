"""
Unified shape inspector for CSV, Excel, and PDF files.

Provides fingerprinting and shape detection for ImportProcess validation.
"""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Any

import pandas as pd

from datalab.imports.parsers import FileParser, FileParserError
from datalab.imports.pdf_inspector import PDFShapeInspector
from datalab.core.serialization import serialize_for_json

logger = logging.getLogger(__name__)


class ShapeInspectorError(Exception):
    """Raised when shape inspection fails."""
    pass


class ShapeInspector:
    """
    Unified shape inspector for CSV, Excel, and PDF files.

    Provides fingerprinting and validation for ImportProcess shape matching.
    """

    def __init__(self):
        self.parser = FileParser()
        self.pdf_inspector = PDFShapeInspector()

    def _infer_column_type(self, series: pd.Series) -> dict[str, Any]:
        """
        Infer column type from sample string values.
        
        Returns:
            {'type': 'string|integer|decimal|boolean|date|datetime', 'format': optional, 'confidence': float}
        """
        import re
        
        # Get non-empty string values
        values = series.dropna().astype(str).str.strip()
        values = values[values != '']
        
        if len(values) == 0:
            return {'type': 'string', 'confidence': 0.0}
        
        sample = values.head(100)
        total = len(sample)
        
        # Check for boolean
        bool_values = {'true', 'false', 'yes', 'no', 'si', 'sí', '1', '0', 'y', 'n', 't', 'f'}
        bool_matches = sum(1 for v in sample if v.lower() in bool_values)
        if bool_matches / total >= 0.9:
            return {'type': 'boolean', 'confidence': bool_matches / total}
        
        # Check for integer
        int_pattern = re.compile(r'^-?\d+$')
        int_matches = sum(1 for v in sample if int_pattern.match(v))
        if int_matches / total >= 0.9:
            return {'type': 'integer', 'confidence': int_matches / total}
        
        # Check for decimal (including comma as decimal separator)
        decimal_pattern = re.compile(r'^-?\d+[.,]\d+$|^-?\d+$')
        decimal_matches = sum(1 for v in sample if decimal_pattern.match(v.replace(',', '.')))
        if decimal_matches / total >= 0.9:
            return {'type': 'decimal', 'confidence': decimal_matches / total}
        
        # Check for date patterns
        date_patterns = [
            (r'^\d{1,2}/\d{1,2}/\d{2,4}$', 'DD/MM/YYYY'),
            (r'^\d{1,2}-\d{1,2}-\d{2,4}$', 'DD-MM-YYYY'),
            (r'^\d{4}-\d{2}-\d{2}$', 'YYYY-MM-DD'),
            (r'^\d{4}/\d{2}/\d{2}$', 'YYYY/MM/DD'),
        ]
        for pattern, fmt in date_patterns:
            date_re = re.compile(pattern)
            date_matches = sum(1 for v in sample if date_re.match(v))
            if date_matches / total >= 0.8:
                return {'type': 'date', 'format': fmt, 'confidence': date_matches / total}
        
        # Check for datetime patterns
        datetime_patterns = [
            (r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', 'YYYY-MM-DD HH:mm:ss'),
            (r'^\d{1,2}/\d{1,2}/\d{2,4} \d{1,2}:\d{2}', 'DD/MM/YYYY HH:mm'),
        ]
        for pattern, fmt in datetime_patterns:
            dt_re = re.compile(pattern)
            dt_matches = sum(1 for v in sample if dt_re.match(v))
            if dt_matches / total >= 0.8:
                return {'type': 'datetime', 'format': fmt, 'confidence': dt_matches / total}
        
        # Default to string
        return {'type': 'string', 'confidence': 1.0}

    def inspect(self, file_obj: Any, file_type: str, filename: str = "") -> dict[str, Any]:
        """
        Inspect a file and return its shape information.

        Args:
            file_obj: File-like object or path to file
            file_type: 'csv', 'excel', or 'pdf'
            filename: Optional filename for better error messages

        Returns:
            dict: {
                'fingerprint': str,  # SHA256 hash of shape
                'description': dict, # Detailed shape description
                'file_type': str
            }

        Raises:
            ShapeInspectorError: If inspection fails
        """
        try:
            if file_type == 'csv':
                return self.inspect_csv(file_obj, filename)
            elif file_type == 'excel':
                return self.inspect_excel(file_obj, filename)
            elif file_type == 'pdf':
                return self.inspect_pdf(file_obj, filename)
            else:
                raise ShapeInspectorError(f"Unsupported file type: {file_type}")

        except Exception as e:
            logger.error(f"Shape inspection failed for {filename or 'file'}: {e}")
            raise ShapeInspectorError(f"Shape inspection failed: {str(e)}") from e

    def inspect_csv(self, file_obj: Any, filename: str = "") -> dict[str, Any]:
        """
        Inspect CSV file shape.

        Fingerprint inputs:
        - delimiter (inferred)
        - header names (normalized, sorted)
        - column count

        Hard fail conditions:
        - No header row found
        - Duplicate column names (after normalization)
        """
        try:
            # Read binary, decode to text for pandas sniffing to avoid regex on bytes
            data_bytes = file_obj.read()
            text_buffer = io.StringIO(data_bytes.decode('utf-8', errors='ignore'))
            file_obj.seek(0)

            # Detect delimiter using csv.Sniffer
            import csv
            text_buffer.seek(0)
            sample_text = text_buffer.read(8192)  # Read first 8KB for sniffing
            text_buffer.seek(0)
            
            try:
                dialect = csv.Sniffer().sniff(sample_text, delimiters=',;\t|')
                detected_delimiter = dialect.delimiter
            except csv.Error:
                detected_delimiter = ','  # Fallback to comma
            
            # Read first few rows using detected delimiter
            sample_df = pd.read_csv(text_buffer, nrows=10, sep=detected_delimiter, engine='python')
            
            # Try to get total row count (quick estimate for small-medium files only)
            total_row_count = None
            try:
                file_size = len(data_bytes)
                if file_size < 10 * 1024 * 1024:
                    # Quick count by reading in chunks from text buffer
                    text_buffer.seek(0)
                    chunk_size = 10000
                    count = 0
                    for chunk in pd.read_csv(text_buffer, chunksize=chunk_size, sep=detected_delimiter, engine='python', header=None, nrows=100000):
                        count += len(chunk)
                        if count >= 100000:
                            break
                    total_row_count = max(0, count - 1)  # Subtract header
            except Exception:
                pass
            
            file_obj.seek(0)  # Reset file pointer

            # Normalize column names (lowercase, strip whitespace)
            normalized_columns = [str(col).strip().lower() for col in sample_df.columns]

            # Check for duplicate column names
            if len(normalized_columns) != len(set(normalized_columns)):
                duplicates = [col for col in normalized_columns if normalized_columns.count(col) > 1]
                raise ShapeInspectorError(f"Duplicate column names in CSV: {list(set(duplicates))}")

            # Create fingerprint from stable elements (use detected delimiter)
            fingerprint_data = {
                'file_type': 'csv',
                'delimiter': detected_delimiter,
                'column_count': len(normalized_columns),
                'columns': sorted(normalized_columns)  # Sort for consistency
            }

            fingerprint = hashlib.sha256(
                str(sorted(fingerprint_data.items())).encode()
            ).hexdigest()

            # Extract sample data (first 10 rows)
            sample_data = []
            for _, row in sample_df.head(10).iterrows():
                sample_data.append({col: serialize_for_json(val) for col, val in row.items()})
            
            # Infer types for each column
            columns_with_types = []
            for orig, norm in zip(sample_df.columns, normalized_columns):
                type_info = self._infer_column_type(sample_df[orig])
                col_def = {
                    'name': orig,
                    'normalized_name': norm,
                    'inferred_type': type_info['type'],
                    'type_confidence': type_info['confidence']
                }
                if 'format' in type_info:
                    col_def['inferred_format'] = type_info['format']
                columns_with_types.append(col_def)
            
            description = {
                'file_type': 'csv',
                'delimiter': detected_delimiter,
                'header_row': 0,  # CSV always assumes header in row 0
                'column_count': len(normalized_columns),
                'columns': columns_with_types,
                'sample_rows': sample_data,
                'total_row_count': total_row_count
            }

            return {
                'fingerprint': fingerprint,
                'description': description,
                'file_type': 'csv'
            }

        except pd.errors.EmptyDataError:
            raise ShapeInspectorError("CSV file is empty")
        except Exception as e:
            raise ShapeInspectorError(f"CSV inspection failed: {str(e)}")

    def inspect_excel(self, file_obj: Any, filename: str = "") -> dict[str, Any]:
        """
        Inspect Excel file shape.

        Fingerprint inputs:
        - sheet names (sorted)
        - header names per sheet (normalized, sorted)
        - column count per sheet
        - header row index per sheet

        Hard fail conditions:
        - Required sheet missing
        - Header row missing in any sheet
        """
        try:
            # Read bytes and use BytesIO so we can safely reread
            data_bytes = file_obj.read()
            buffer = pd.ExcelFile(io.BytesIO(data_bytes))

            sheet_info = {}
            for sheet_name in buffer.sheet_names:
                # Auto-detect header row: find first row with >=1 non-null cell (within first 20 rows)
                detect_df = pd.read_excel(buffer, sheet_name=sheet_name, nrows=20, header=None)
                header_row_idx = 0
                for idx in range(len(detect_df)):
                    row = detect_df.iloc[idx]
                    if row.count() > 0:
                        header_row_idx = idx
                        break

                # Read with detected header
                sample_df = pd.read_excel(buffer, sheet_name=sheet_name, nrows=10 + header_row_idx + 1, header=header_row_idx)
                normalized_columns = [str(col).strip().lower() for col in sample_df.columns]

                # Check for duplicates
                if len(normalized_columns) != len(set(normalized_columns)):
                    duplicates = [col for col in normalized_columns if normalized_columns.count(col) > 1]
                    raise ShapeInspectorError(f"Duplicate columns in sheet '{sheet_name}': {list(set(duplicates))}")

                # Try to get total row count for this sheet
                total_row_count = None
                try:
                    full_df = pd.read_excel(buffer, sheet_name=sheet_name, header=header_row_idx)
                    total_row_count = len(full_df)
                except Exception:
                    pass

                # Extract sample data (first 10 rows after header)
                sample_data = []
                for _, row in sample_df.head(10).iterrows():
                    sample_data.append({col: serialize_for_json(val) for col, val in row.items()})
                
                sheet_info[sheet_name] = {
                    'column_count': len(normalized_columns),
                    'columns': [
                        {'name': orig, 'normalized_name': norm}
                        for orig, norm in zip(sample_df.columns, normalized_columns)
                    ],
                    'header_row': header_row_idx,
                    'skip_rows': header_row_idx,
                    'sample_rows': sample_data,
                    'total_row_count': total_row_count
                }

            # Create fingerprint from stable elements
            fingerprint_data = {
                'file_type': 'excel',
                'sheets': sorted(excel_file.sheet_names),
                'sheet_info': {sheet: info['columns'] for sheet, info in sheet_info.items()}
            }

            fingerprint = hashlib.sha256(
                str(sorted(fingerprint_data.items())).encode()
            ).hexdigest()

            description = {
                'file_type': 'excel',
                'sheets': buffer.sheet_names,
                'sheet_details': sheet_info
            }

            return {
                'fingerprint': fingerprint,
                'description': description,
                'file_type': 'excel'
            }

        except Exception as e:
            raise ShapeInspectorError(f"Excel inspection failed: {str(e)}")

    def inspect_pdf(self, file_obj: Any, filename: str = "") -> dict[str, Any]:
        """
        Inspect PDF file shape using PDFShapeInspector.

        Fingerprint excludes page count for stability.
        """
        # PDFShapeInspector.inspect() only takes file_obj, not filename
        return self.pdf_inspector.inspect(file_obj)

    def validate_shape_match(self, detected_shape: dict, expected_fingerprint: str) -> dict[str, Any]:
        """
        Validate if detected shape matches expected fingerprint.

        Args:
            detected_shape: Result from inspect() method
            expected_fingerprint: Expected SHA256 fingerprint

        Returns:
            dict: {
                'status': 'pass' | 'fail',
                'score': float,  # 1.0 for exact match, 0.0 for no match
                'reasons': list[str]  # Failure reasons if any
            }
        """
        detected_fingerprint = detected_shape['fingerprint']

        if detected_fingerprint == expected_fingerprint:
            return {
                'status': 'pass',
                'score': 1.0,
                'reasons': []
            }
        else:
            return {
                'status': 'fail',
                'score': 0.0,
                'reasons': [f"Fingerprint mismatch: expected {expected_fingerprint[:16]}..., got {detected_fingerprint[:16]}..."]
            }