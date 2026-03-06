"""
Validation utilities for ImportContract.
"""
from __future__ import annotations

from typing import Any


class ImportContractValidationError(Exception):
    """Raised when ImportContract validation fails."""
    pass


class ImportContractValidator:
    """Validates ImportContract JSON."""
    
    ALLOWED_PARSER_TYPES = ['csv', 'excel', 'pdf']
    ALLOWED_COLUMN_TYPES = ['date', 'datetime', 'decimal', 'integer', 'string', 'boolean']
    ALLOWED_CLEANING_RULES = [
        'trim',
        'upper',
        'lower',
        'currency_to_decimal',
        'remove_accents'
    ]
    ALLOWED_DEDUPE_STRATEGIES = ['keep_first', 'keep_last', 'reject']
    
    def validate(self, contract: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate ImportContract JSON.
        
        Args:
            contract: ImportContract JSON dictionary
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors: list[str] = []
        
        # Validate version
        if contract.get('version') != '1':
            errors.append("Version must be '1'")
        
        # Validate parser
        parser = contract.get('parser', {})
        if not parser:
            errors.append("Parser configuration is required")
        else:
            parser_type = parser.get('type')
            if parser_type not in self.ALLOWED_PARSER_TYPES:
                errors.append(
                    f"Parser type must be one of {self.ALLOWED_PARSER_TYPES}, "
                    f"got '{parser_type}'"
                )
            
            if parser_type in ('csv', 'excel'):
                # Validate header_row (should be 0-based integer >= 0)
                header_row = parser.get('header_row')
                if header_row is not None:
                    if not isinstance(header_row, int) or header_row < 0:
                        errors.append("header_row must be a non-negative integer")
                
                # Validate skip_rows (should be non-negative integer)
                skip_rows = parser.get('skip_rows', 0)
                if not isinstance(skip_rows, int) or skip_rows < 0:
                    errors.append("skip_rows must be a non-negative integer")
                
                # Validate delimiter (optional, only for CSV)
                delimiter = parser.get('delimiter')
                if delimiter is not None:
                    if not isinstance(delimiter, str) or len(delimiter) != 1:
                        errors.append("delimiter must be a single character string")
                
                # Validate date_format (optional)
                date_format = parser.get('date_format')
                if date_format is not None:
                    if not isinstance(date_format, str):
                        errors.append("date_format must be a string")
                
                # Validate datetime_format (optional)
                datetime_format = parser.get('datetime_format')
                if datetime_format is not None:
                    if not isinstance(datetime_format, str):
                        errors.append("datetime_format must be a string")

            if parser_type == 'pdf':
                structural_unit = parser.get('structural_unit') or contract.get('structural_unit')
                if not structural_unit:
                    errors.append("PDF parser requires 'structural_unit' definition")
                else:
                    selector = structural_unit.get('selector', {})
                    bbox = selector.get('bbox')
                    page_selector = selector.get('page_selector', {})
                    if not bbox or not isinstance(bbox, list) or len(bbox) != 4:
                        errors.append("structural_unit.selector.bbox must be a list of four numbers")
                    if not page_selector or not isinstance(page_selector, dict):
                        errors.append("structural_unit.selector.page_selector must be provided")
        
        # Validate mapping
        mapping = contract.get('mapping', [])
        if not mapping:
            errors.append("Mapping cannot be empty")
        else:
            if not isinstance(mapping, list):
                errors.append("Mapping must be a list")
            else:
                for i, map_item in enumerate(mapping):
                    if not isinstance(map_item, dict):
                        errors.append(f"Mapping item {i} must be a dictionary")
                        continue
                    
                    if not map_item.get('source'):
                        errors.append(f"Mapping item {i} must have 'source' field")
                    
                    if not map_item.get('target'):
                        errors.append(f"Mapping item {i} must have 'target' field")
                    
                    col_type = map_item.get('type')
                    if col_type not in self.ALLOWED_COLUMN_TYPES:
                        errors.append(
                            f"Mapping item {i}: type must be one of "
                            f"{self.ALLOWED_COLUMN_TYPES}, got '{col_type}'"
                        )
                    
                    # Validate format (optional, mainly for date types)
                    format_str = map_item.get('format')
                    if format_str is not None:
                        if not isinstance(format_str, str):
                            errors.append(f"Mapping item {i}: 'format' must be a string")
                        elif col_type == 'date' and not format_str:
                            errors.append(f"Mapping item {i}: 'format' cannot be empty for date type")
                    
                    # Validate cleaning rules
                    clean_rules = map_item.get('clean', [])
                    if clean_rules:
                        if not isinstance(clean_rules, list):
                            errors.append(f"Mapping item {i}: 'clean' must be a list")
                        else:
                            for rule in clean_rules:
                                if rule not in self.ALLOWED_CLEANING_RULES:
                                    errors.append(
                                        f"Mapping item {i}: Unknown cleaning rule '{rule}'. "
                                        f"Allowed: {self.ALLOWED_CLEANING_RULES}"
                                    )
        
        # Validate dedupe (optional)
        dedupe = contract.get('dedupe')
        if dedupe:
            if not isinstance(dedupe, dict):
                errors.append("dedupe must be a dictionary")
            else:
                keys = dedupe.get('keys', [])
                if not isinstance(keys, list) or not keys:
                    errors.append("dedupe.keys must be a non-empty list")
                
                strategy = dedupe.get('strategy')
                if strategy and strategy not in self.ALLOWED_DEDUPE_STRATEGIES:
                    errors.append(
                        f"dedupe.strategy must be one of {self.ALLOWED_DEDUPE_STRATEGIES}, "
                        f"got '{strategy}'"
                    )
        
        return len(errors) == 0, errors
    
    def validate_and_raise(self, contract: dict[str, Any]) -> None:
        """
        Validate ImportContract and raise exception if invalid.
        
        Args:
            contract: ImportContract JSON dictionary
            
        Raises:
            ImportContractValidationError: If validation fails
        """
        is_valid, errors = self.validate(contract)
        if not is_valid:
            error_msg = "ImportContract validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ImportContractValidationError(error_msg)
