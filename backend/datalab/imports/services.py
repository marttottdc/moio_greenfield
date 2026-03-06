"""
Import execution services for Data Lab.

Handles execution of ImportContracts with incremental accumulation support.
"""
from __future__ import annotations

import logging
import hashlib
import json
from typing import Any
from uuid import UUID

import boto3
import pandas as pd
from django.db import models
from django.conf import settings
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model

from datalab.core.models import (
    AccumulationLog,
    FileAsset,
    FileSet,
    ResultSet,
    ResultSetOrigin,
    ResultSetStorage,
    Snapshot,
)
from datalab.core.serialization import serialize_for_json
from datalab.core.storage import get_storage
from datalab.imports.parsers import FileParser, FileParserError
from datalab.imports.pdf_extractor import PDFExtractor
from datalab.imports.contracts import ImportContractV1
from datalab.imports.shape_inspector import ShapeInspector, ShapeInspectorError

User = get_user_model()
logger = logging.getLogger(__name__)


class ImportExecutorError(Exception):
    """Raised when import execution fails."""
    pass


def convert_date_format(contract_format: str) -> str:
    """
    Convert contract date/datetime format to Python strptime format.
    
    Supports both date and datetime formats:
    Date formats:
    - DD/MM/YYYY -> %d/%m/%Y
    - MM/DD/YYYY -> %m/%d/%Y
    - YYYY-MM-DD -> %Y-%m-%d
    - DD-MM-YYYY -> %d-%m-%Y
    - DD.MM.YYYY -> %d.%m.%Y
    
    Datetime formats:
    - YYYY-MM-DD HH:mm:ss -> %Y-%m-%d %H:%M:%S
    - DD/MM/YYYY HH:mm:ss -> %d/%m/%Y %H:%M:%S
    - YYYY-MM-DD HH:mm -> %Y-%m-%d %H:%M
    
    Args:
        contract_format: Date/datetime format string from contract (e.g., 'DD/MM/YYYY' or 'YYYY-MM-DD HH:mm:ss')
        
    Returns:
        Python strptime format string (e.g., '%d/%m/%Y' or '%Y-%m-%d %H:%M:%S')
    """
    if not contract_format:
        return None
    
    # Common format mappings
    format_map = {
        # Date formats
        'DD/MM/YYYY': '%d/%m/%Y',
        'MM/DD/YYYY': '%m/%d/%Y',
        'YYYY-MM-DD': '%Y-%m-%d',
        'YYYY/MM/DD': '%Y/%m/%d',
        'DD-MM-YYYY': '%d-%m-%Y',
        'MM-DD-YYYY': '%m-%d-%Y',
        'DD.MM.YYYY': '%d.%m.%Y',
        'MM.DD.YYYY': '%m.%d.%Y',
        'DD/MM/YY': '%d/%m/%y',
        'MM/DD/YY': '%m/%d/%y',
        'YYYYMMDD': '%Y%m%d',
        'DDMMYYYY': '%d%m%Y',
        'MMDDYYYY': '%m%d%Y',
        # Datetime formats
        'YYYY-MM-DD HH:mm:ss': '%Y-%m-%d %H:%M:%S',
        'DD/MM/YYYY HH:mm:ss': '%d/%m/%Y %H:%M:%S',
        'MM/DD/YYYY HH:mm:ss': '%m/%d/%Y %H:%M:%S',
        'YYYY-MM-DD HH:mm': '%Y-%m-%d %H:%M',
        'DD/MM/YYYY HH:mm': '%d/%m/%Y %H:%M',
        'MM/DD/YYYY HH:mm': '%m/%d/%Y %H:%M',
    }
    
    # Check if exact match exists
    if contract_format in format_map:
        return format_map[contract_format]
    
    # Try to convert common patterns
    converted = contract_format
    
    # Replace common date components
    replacements = {
        'YYYY': '%Y',  # 4-digit year
        'YY': '%y',    # 2-digit year
        'MM': '%m',    # Month (01-12)
        'DD': '%d',    # Day (01-31)
        'HH': '%H',    # Hour (00-23)
        'mm': '%M',    # Minute (00-59)
        'ss': '%S',    # Second (00-59)
    }
    
    for pattern, replacement in replacements.items():
        converted = converted.replace(pattern, replacement)
    
    # If no replacements were made, return as-is (might already be Python format)
    if converted == contract_format:
        logger.warning(f"Unknown date format '{contract_format}', using as-is")
        return contract_format
    
    return converted


class ImportExecutor:
    """
    Executes ImportContracts on files or filesets.
    
    Supports incremental accumulation for FileSets.
    """
    
    THRESHOLD_ROWS = 10000  # Materialize if > 10k rows
    PREVIEW_LIMIT = 200  # Limit preview to 200 rows
    
    def __init__(self):
        self.parser = FileParser()
        self.pdf_extractor = PDFExtractor()
        self.storage = get_storage()
        
        # Initialize S3 client for file access
        self.s3_client = boto3.client(
            's3',
            region_name=settings.AWS_S3_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.bucket_name = settings.AWS_STORAGE_MEDIA_BUCKET_NAME
    
    def execute(
        self,
        source: dict[str, Any],
        contract_json: dict[str, Any],
        materialize: bool = False,
        rebuild: bool = False,
        accumulation: dict[str, Any] | None = None,
        user: User | None = None,
        import_data_as_json: bool = False
    ) -> ResultSet:
        """
        Execute ImportContract on a file or fileset.
        
        Args:
            source: {'file_id': UUID} or {'fileset_id': UUID}
            contract_json: Complete ImportContract JSON
            materialize: Force materialization as Parquet
            rebuild: If True, process all files from scratch (ignore accumulation)
            accumulation: Optional accumulation config {'strategy': 'append|merge', 'dedupe_keys': [...]}
            user: User executing the import
            
        Returns:
            ResultSet with imported data
            
        Raises:
            ImportExecutorError: If execution fails
        """
        # Validate contract using Pydantic schema
        try:
            contract = ImportContractV1.model_validate(contract_json)
        except Exception as e:
            raise ImportExecutorError(f"Invalid contract: {str(e)}") from e

        contract_hash = hashlib.sha256(json.dumps(contract_json, sort_keys=True).encode()).hexdigest()

        # Get tenant from source
        tenant = self._get_tenant_from_source(source)

        # Process source
        if 'fileset_id' in source:
            combined_data = self._process_fileset(
                source['fileset_id'],
                contract_json,
                rebuild,
                accumulation,
                import_data_as_json=import_data_as_json
            )
        elif 'file_id' in source:
            file_asset = FileAsset.objects.get(id=source['file_id'], tenant=tenant)
            combined_data = self._parse_file(file_asset, contract_json, import_data_as_json=import_data_as_json)
        else:
            raise ImportExecutorError("source must have 'file_id' or 'fileset_id'")
        
        if not import_data_as_json:
            # Apply contract (mapping, type casts, cleaning)
            combined_data = self._apply_contract(combined_data, contract_json)
            # Apply dedupe if specified
            combined_data = self._apply_dedupe(combined_data, contract_json.get('dedupe'))
        
        # Create ResultSet
        resultset = self._create_resultset(
            combined_data,
            source,
            contract_json,
            tenant,
            user,
            contract_hash=contract_hash,
            is_json_object=import_data_as_json
        )
        
        # Materialize if needed (only for tabular DataFrame)
        if (not import_data_as_json) and (materialize or resultset.row_count > self.THRESHOLD_ROWS):
            self._materialize_resultset(resultset, combined_data)
        
        if not import_data_as_json:
            # Generate preview - convert Timestamps to ISO strings for JSON serialization
            preview_df = combined_data.head(self.PREVIEW_LIMIT)
            preview_dict = preview_df.to_dict(orient='records')
            resultset.preview_json = serialize_for_json(preview_dict)
            resultset.save()
        
        # Create Snapshot and AccumulationLog if FileSet
        if 'fileset_id' in source and not rebuild:
            fileset = FileSet.objects.get(id=source['fileset_id'], tenant=tenant)
            snapshot = self._create_snapshot(resultset, fileset, user)
            self._log_accumulation(
                snapshot,
                fileset,
                self._get_processed_files(fileset, rebuild),
                combined_df,
                rebuild
            )
        
        return resultset
    
    def _process_fileset(
        self,
        fileset_id: UUID,
        contract_json: dict[str, Any],
        rebuild: bool,
        accumulation: dict[str, Any] | None,
        import_data_as_json: bool = False
    ):
        """Process FileSet with accumulation logic."""
        fileset = FileSet.objects.get(id=fileset_id)
        tenant = fileset.tenant
        
        if rebuild:
            # Rebuild: process all files from scratch
            all_files = fileset.files.all()
            logger.info(f"Rebuilding FileSet {fileset_id}: processing {all_files.count()} files")
            dfs = [self._parse_file(f, contract_json, import_data_as_json=import_data_as_json) for f in all_files]
            if not dfs:
                raise ImportExecutorError(f"FileSet {fileset_id} has no files")
            combined_df = pd.concat(dfs, ignore_index=True)
        else:
            # Incremental accumulation
            last_snapshot = self._get_last_snapshot_for_fileset(fileset)
            
            if last_snapshot:
                # Load base DataFrame from snapshot
                logger.info(f"Loading base snapshot {last_snapshot.id} for FileSet {fileset_id}")
                base_df = self._load_snapshot_as_dataframe(last_snapshot)
                
                # Find processed files
                last_log = AccumulationLog.objects.filter(
                    snapshot=last_snapshot,
                    fileset=fileset
                ).first()
                
                processed_file_ids = set()
                if last_log:
                    processed_file_ids = set(
                        last_log.processed_files.values_list('id', flat=True)
                    )
                
                # Find new files
                new_files = fileset.files.exclude(id__in=processed_file_ids)
                
                if new_files.exists():
                    logger.info(
                        f"Incremental import: processing {new_files.count()} new files "
                        f"(already processed {len(processed_file_ids)} files)"
                    )
                    # Process only new files
                    new_dfs = [self._parse_file(f, contract_json, import_data_as_json=import_data_as_json) for f in new_files]
                    new_df = pd.concat(new_dfs, ignore_index=True)
                    
                    # Merge according to strategy
                    strategy = (accumulation or {}).get('strategy', 'append')
                    if strategy == 'append':
                        combined_df = pd.concat([base_df, new_df], ignore_index=True)
                    elif strategy == 'merge':
                        dedupe_keys = (accumulation or {}).get('dedupe_keys', [])
                        if not dedupe_keys:
                            raise ImportExecutorError(
                                "merge strategy requires 'dedupe_keys' in accumulation config"
                            )
                        combined_df = self._merge_on_keys(base_df, new_df, dedupe_keys)
                    else:
                        raise ImportExecutorError(f"Unknown accumulation strategy: {strategy}")
                else:
                    logger.info(f"No new files to process for FileSet {fileset_id}")
                    combined_df = base_df
            else:
                # First import: process all files
                logger.info(f"First import for FileSet {fileset_id}: processing all files")
                all_files = fileset.files.all()
                if not all_files.exists():
                    raise ImportExecutorError(f"FileSet {fileset_id} has no files")
                dfs = [self._parse_file(f, contract_json) for f in all_files]
                combined_df = pd.concat(dfs, ignore_index=True)
        
        if import_data_as_json:
            return self._dataframe_to_json_object(combined_df, contract_json)
        return combined_df
    
    def _parse_file(self, file_asset: FileAsset, contract_json: dict[str, Any], import_data_as_json: bool = False):
        """Parse a single file according to contract."""
        parser_config = contract_json.get('parser', {})
        parser_type = parser_config.get('type')
        
        # Download file from S3 using default_storage to handle location prefix correctly
        from django.core.files.storage import default_storage
        
        try:
            # Use default_storage.open() which handles the location prefix automatically
            file_obj = default_storage.open(file_asset.storage_key, 'rb')
        except Exception as e:
            raise ImportExecutorError(f"Failed to load file {file_asset.id} from S3: {e}") from e
        
        try:
            if parser_type == 'csv':
                df = self.parser.parse_csv(
                    file_obj,
                    header_row=parser_config.get('header_row', 0),
                    skip_rows=parser_config.get('skip_rows', 0),
                    range_config=parser_config.get('range'),
                    delimiter=parser_config.get('delimiter', ','),
                    encoding=parser_config.get('encoding', 'utf-8')
                )
                return self._dataframe_to_json_object(df, contract_json) if import_data_as_json else df
            elif parser_type == 'excel':
                df = self.parser.parse_excel(
                    file_obj,
                    sheet=parser_config.get('sheet', 0),
                    header_row=parser_config.get('header_row', 0),
                    skip_rows=parser_config.get('skip_rows', 0),
                    range_config=parser_config.get('range')
                )
                return self._dataframe_to_json_object(df, contract_json) if import_data_as_json else df
            elif parser_type == 'pdf':
                structural_unit = parser_config.get('structural_unit') or contract_json.get('structural_unit')
                if not structural_unit:
                    raise ImportExecutorError("PDF parser requires 'structural_unit' in parser or contract")
                if import_data_as_json:
                    return self.pdf_extractor.extract_pdf_as_json(
                        file_obj,
                        structural_unit=structural_unit
                    )
                return self.parser.parse_pdf(
                    file_obj,
                    structural_unit=structural_unit
                )
            else:
                raise ImportExecutorError(f"Unsupported parser type: {parser_type}")
        except FileParserError as e:
            raise ImportExecutorError(f"Failed to parse file {file_asset.filename}: {e}") from e
        finally:
            file_obj.close()
    
    def _dataframe_to_json_object(self, df: pd.DataFrame, contract_json: dict[str, Any]) -> dict[str, Any]:
        """Convert a DataFrame into a JSON Object structure for scripts."""
        return {
            "columns": df.columns.tolist(),
            "rows": serialize_for_json(df.to_dict(orient='records')),
            "row_count": len(df),
            "source_parser": contract_json.get('parser', {}).get('type'),
        }

    def _compute_row_count_from_json(self, json_obj: Any, file_type: str) -> int:
        """Best-effort row count from JSON Object."""
        try:
            if isinstance(json_obj, dict):
                if "row_count" in json_obj and isinstance(json_obj["row_count"], int):
                    return json_obj["row_count"]
                if file_type in ['csv', 'excel'] and "rows" in json_obj:
                    return len(json_obj.get("rows", []))
                if file_type == 'pdf' and "pages" in json_obj:
                    total = 0
                    for page in json_obj.get("pages", []):
                        for table in page.get("tables", []):
                            if isinstance(table, list) and len(table) > 1:
                                total += len(table) - 1  # exclude header
                    return total
        except Exception:
            return 0
        return 0

    def _apply_contract(self, df: pd.DataFrame, contract_json: dict[str, Any]) -> pd.DataFrame:
        """Apply mapping, type casts, and cleaning rules."""
        mapping = contract_json.get('mapping', [])
        parser_config = contract_json.get('parser', {})
        
        # Get default date/datetime formats from parser config
        default_date_format = parser_config.get('date_format')
        default_datetime_format = parser_config.get('datetime_format')
        
        if not mapping:
            return df
        
        # Build new DataFrame with mapped columns
        result_data = {}
        
        for map_item in mapping:
            source_col = map_item['source']
            target_col = map_item['target']
            col_type = map_item['type']
            clean_rules = map_item.get('clean', [])
            
            # Get format: field-level format takes precedence over parser-level format
            format_str = map_item.get('format')
            if not format_str:
                # Use parser-level format based on column type
                if col_type == 'date':
                    format_str = default_date_format
                elif col_type == 'datetime':
                    format_str = default_datetime_format
            
            if source_col not in df.columns:
                logger.warning(f"Source column '{source_col}' not found, skipping")
                continue
            
            # Get source series
            series = df[source_col].copy()
            
            # Apply cleaning rules
            for rule in clean_rules:
                if rule == 'trim':
                    series = series.astype(str).str.strip()
                elif rule == 'upper':
                    series = series.astype(str).str.upper()
                elif rule == 'lower':
                    series = series.astype(str).str.lower()
                elif rule == 'remove_accents':
                    # Simple implementation, could use unidecode library
                    series = series.astype(str).str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('ascii')
                elif rule == 'currency_to_decimal':
                    # Remove currency symbols and convert to decimal
                    series = series.astype(str).str.replace(r'[\$,\s]', '', regex=True)
            
            # Apply type casting
            if col_type == 'integer':
                series = pd.to_numeric(series, errors='coerce').astype('Int64')
            elif col_type == 'decimal':
                series = pd.to_numeric(series, errors='coerce')
            elif col_type == 'boolean':
                series = series.astype(str).str.lower().isin(['true', '1', 'yes', 'y']).astype('boolean')
            elif col_type == 'date':
                if format_str:
                    # Convert contract format (e.g., 'DD/MM/YYYY') to Python format (e.g., '%d/%m/%Y')
                    python_format = convert_date_format(format_str)
                    series = pd.to_datetime(series, format=python_format, errors='coerce')
                else:
                    # Try to infer format automatically
                    series = pd.to_datetime(series, errors='coerce')
            elif col_type == 'datetime':
                if format_str:
                    # Convert contract format to Python format
                    python_format = convert_date_format(format_str)
                    series = pd.to_datetime(series, format=python_format, errors='coerce')
                else:
                    # Try to infer format automatically
                    series = pd.to_datetime(series, errors='coerce')
            # 'string' doesn't need conversion
            
            result_data[target_col] = series
        
        return pd.DataFrame(result_data)
    
    def _apply_dedupe(self, df: pd.DataFrame, dedupe_config: dict[str, Any] | None) -> pd.DataFrame:
        """Apply deduplication if configured."""
        if not dedupe_config:
            return df
        
        keys = dedupe_config.get('keys', [])
        strategy = dedupe_config.get('strategy', 'keep_last')
        
        if not keys:
            return df
        
        # Check that all keys exist
        missing_keys = [k for k in keys if k not in df.columns]
        if missing_keys:
            logger.warning(f"Dedupe keys not found: {missing_keys}")
            return df
        
        if strategy == 'keep_first':
            return df.drop_duplicates(subset=keys, keep='first')
        elif strategy == 'keep_last':
            return df.drop_duplicates(subset=keys, keep='last')
        elif strategy == 'reject':
            # Remove all duplicates (keep none)
            duplicates = df.duplicated(subset=keys, keep=False)
            return df[~duplicates]
        else:
            logger.warning(f"Unknown dedupe strategy: {strategy}")
            return df
    
    def _create_resultset(
        self,
        data: Any,
        source: dict[str, Any],
        contract_json: dict[str, Any],
        tenant,
        user: User | None,
        contract_hash: str | None = None,
        is_json_object: bool = False
    ) -> ResultSet:
        """Create ResultSet from DataFrame or JSON Object."""
        # Build lineage (minimum required)
        lineage = {
            'origin': ResultSetOrigin.IMPORT,
            'source': source,
            'contract_version': contract_json.get('version', '1'),
            'contract_hash': contract_hash or hashlib.sha256(json.dumps(contract_json, sort_keys=True).encode()).hexdigest(),
        }

        if is_json_object:
            schema = {"type": "json_object", "file_type": contract_json.get('parser', {}).get('type')}
            row_count = self._compute_row_count_from_json(data, contract_json.get('parser', {}).get('type'))
            resultset = ResultSet.objects.create(
                tenant=tenant,
                origin=ResultSetOrigin.IMPORT,
                schema_json=schema,
                row_count=row_count,
                storage=ResultSetStorage.MEMORY,
                lineage_json=lineage,
                preview_json=serialize_for_json(data),
                is_json_object=True,
                created_by=user
            )
            return resultset

        # Detect schema for tabular data
        schema = self.parser.detect_schema(data)

        # Create ResultSet for tabular DataFrame
        resultset = ResultSet.objects.create(
            tenant=tenant,
            origin=ResultSetOrigin.IMPORT,
            schema_json=schema,
            row_count=len(data),
            storage=ResultSetStorage.MEMORY,
            lineage_json=lineage,
            created_by=user
        )

        return resultset
    
    def _materialize_resultset(self, resultset: ResultSet, df: pd.DataFrame) -> None:
        """Materialize ResultSet as Parquet in S3."""
        try:
            storage_key = self.storage.save_parquet(df, resultset.id)
            resultset.storage = ResultSetStorage.PARQUET
            resultset.storage_key = storage_key
            resultset.save(update_fields=['storage', 'storage_key'])
            logger.info(f"Materialized ResultSet {resultset.id} as Parquet")
        except Exception as e:
            logger.error(f"Failed to materialize ResultSet {resultset.id}: {e}")
            # Don't fail the import, just log the error
    
    def _get_last_snapshot_for_fileset(self, fileset: FileSet) -> Snapshot | None:
        """Get the last Snapshot for a FileSet."""
        return fileset.last_snapshot
    
    def _load_snapshot_as_dataframe(self, snapshot: Snapshot) -> pd.DataFrame:
        """Load Snapshot's ResultSet as DataFrame."""
        resultset = snapshot.resultset
        
        if resultset.storage == ResultSetStorage.PARQUET.value:
            # Load from S3
            return self.storage.load_parquet(resultset.id)
        else:
            # Reconstruct from preview (limited)
            # For memory storage, we'd need to store the full data elsewhere
            # For now, this is a limitation
            raise ImportExecutorError(
                f"Cannot load Snapshot {snapshot.id}: ResultSet is not materialized as Parquet"
            )
    
    def _merge_on_keys(self, base_df: pd.DataFrame, new_df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        """Merge new DataFrame into base DataFrame on specified keys."""
        # Check keys exist
        for key in keys:
            if key not in base_df.columns or key not in new_df.columns:
                raise ImportExecutorError(f"Merge key '{key}' not found in DataFrames")
        
        # Merge: keep last occurrence (new_df takes precedence)
        merged = pd.merge(
            base_df,
            new_df,
            on=keys,
            how='outer',
            suffixes=('_old', '_new'),
            indicator=True
        )
        
        # Prioritize new values
        for col in new_df.columns:
            if col not in keys:
                if f"{col}_new" in merged.columns:
                    merged[col] = merged[f"{col}_new"].fillna(merged.get(f"{col}_old", pd.Series()))
                elif f"{col}_old" in merged.columns:
                    merged[col] = merged[f"{col}_old"]
        
        # Drop helper columns
        merged = merged.drop(columns=[col for col in merged.columns if col.endswith('_old') or col.endswith('_new')])
        merged = merged.drop(columns=['_merge'])
        
        return merged.reset_index(drop=True)
    
    def _create_snapshot(
        self,
        resultset: ResultSet,
        fileset: FileSet,
        user: User | None
    ) -> Snapshot:
        """Create Snapshot for FileSet."""
        # Determine version
        last_snapshot = fileset.last_snapshot
        if last_snapshot:
            version = last_snapshot.version + 1
        else:
            version = 1
        
        # Generate snapshot name
        snapshot_name = f"{fileset.name}_snapshot"
        
        snapshot = Snapshot.objects.create(
            tenant=fileset.tenant,
            name=snapshot_name,
            version=version,
            resultset=resultset,
            fileset=fileset,
            created_by=user
        )
        
        # Update FileSet's last_snapshot
        fileset.last_snapshot = snapshot
        fileset.save(update_fields=['last_snapshot'])
        
        return snapshot
    
    def _log_accumulation(
        self,
        snapshot: Snapshot,
        fileset: FileSet,
        processed_files: list[FileAsset],
        df: pd.DataFrame,
        is_rebuild: bool
    ) -> AccumulationLog:
        """Create AccumulationLog for tracking."""
        last_log = AccumulationLog.objects.filter(
            fileset=fileset
        ).order_by('-created_at').first()
        
        row_count_added = len(df)
        if last_log and not is_rebuild:
            # Calculate only new rows added
            row_count_added = len(df) - last_log.row_count_total
        
        log = AccumulationLog.objects.create(
            tenant=fileset.tenant,
            snapshot=snapshot,
            fileset=fileset,
            row_count_added=row_count_added,
            row_count_total=len(df),
            is_rebuild=is_rebuild
        )
        
        # Add processed files
        log.processed_files.set(processed_files)
        
        return log
    
    def _get_processed_files(self, fileset: FileSet, rebuild: bool) -> list[FileAsset]:
        """Get list of processed files."""
        if rebuild:
            return list(fileset.files.all())
        else:
            # Get new files only
            last_snapshot = self._get_last_snapshot_for_fileset(fileset)
            if last_snapshot:
                last_log = AccumulationLog.objects.filter(
                    snapshot=last_snapshot,
                    fileset=fileset
                ).first()
                if last_log:
                    processed_file_ids = set(last_log.processed_files.values_list('id', flat=True))
                    return list(fileset.files.exclude(id__in=processed_file_ids))
            return list(fileset.files.all())
    
    def _get_tenant_from_source(self, source: dict[str, Any]) -> Any:
        """Get tenant from source."""
        if 'fileset_id' in source:
            fileset = FileSet.objects.get(id=source['fileset_id'])
            return fileset.tenant
        elif 'file_id' in source:
            file_asset = FileAsset.objects.get(id=source['file_id'])
            return file_asset.tenant
        else:
            raise ImportExecutorError("Invalid source: must have 'file_id' or 'fileset_id'")


# ===== v3.1 ImportProcess Control Plane =====

class ImportProcessService:
    """
    Service for managing ImportProcess execution and lifecycle.

    Provides the v3.1 control plane with shape validation, versioning,
    and deterministic execution flow.
    """

    def __init__(self):
        self.shape_inspector = ShapeInspector()
        self.import_executor = ImportExecutor()

    def create_import_process(
        self,
        tenant,
        name: str,
        file_type: str,
        shape_fingerprint: str,
        shape_description: dict,
        structural_units: list = None,
        semantic_derivations: list = None,
        import_data_as_json: bool = False,
        contract_json: dict = None
    ):
        """
        Create a new ImportProcess.

        Args:
            tenant: Tenant instance
            name: Process name
            file_type: 'csv', 'excel', or 'pdf'
            shape_fingerprint: SHA256 fingerprint of expected shape
            shape_description: Detailed shape description
            structural_units: List of structural unit definitions
            semantic_derivations: List of semantic derivation definitions
            import_data_as_json: If True, store data as JSON instead of DataFrame
            contract_json: Complete import contract (optional, will be initialized from shape if not provided)

        Returns:
            ImportProcess: Created process
        """
        from datalab.core.models import ImportProcess

        # Determine version (increment from latest)
        latest_version = ImportProcess.objects.filter(
            tenant=tenant,
            name=name
        ).aggregate(max_version=models.Max('version'))['max_version'] or 0

        # Initialize contract_json from shape_description if not provided
        if contract_json is None:
            contract_json = self._build_initial_contract(file_type, shape_description)

        process = ImportProcess.objects.create(
            tenant=tenant,
            name=name,
            file_type=file_type,
            shape_fingerprint=shape_fingerprint,
            shape_description=shape_description,
            structural_units=structural_units or [],
            semantic_derivations=semantic_derivations or [],
            contract_json=contract_json,
            version=latest_version + 1,
            import_data_as_json=import_data_as_json,
        )

        return process

    def _build_initial_contract(self, file_type: str, shape_description: dict) -> dict:
        """
        Build an initial import contract from shape description.
        
        The contract is initialized with detected parser settings and 
        mapping using inferred types from shape inspection.
        User can then edit the mapping to customize types, formats, and cleaning.
        """
        # Parser config from shape
        parser_config = {
            'type': file_type,
            'header_row': shape_description.get('header_row', 0),
            'skip_rows': shape_description.get('skip_rows', 0),
        }
        
        # Add file-type specific settings
        if file_type == 'csv':
            parser_config['delimiter'] = shape_description.get('delimiter', ',')
        elif file_type == 'excel':
            parser_config['sheet'] = shape_description.get('sheet', 0)
        
        # Build mapping using inferred types from shape inspection
        mapping = []
        columns = shape_description.get('columns', [])
        for col_info in columns:
            if isinstance(col_info, dict):
                col_name = col_info.get('name', col_info.get('normalized_name', ''))
                # Use inferred type if available, otherwise default to string
                col_type = col_info.get('inferred_type', 'string')
                col_format = col_info.get('inferred_format')
            else:
                col_name = str(col_info)
                col_type = 'string'
                col_format = None
            
            if col_name:
                map_entry = {
                    'source': col_name,
                    'target': col_name,
                    'type': col_type,
                    'clean': []
                }
                if col_format:
                    map_entry['format'] = col_format
                mapping.append(map_entry)
        
        return {
            'version': '1',
            'parser': parser_config,
            'mapping': mapping
        }

    def run_import_process(
        self,
        import_process,
        raw_dataset,
        user=None
    ):
        """
        Execute an ImportProcess against a RawDataset.

        Enforces strict execution order:
        1. Shape inspection
        2. Shape validation (fail-fast)
        3. Extract StructuralUnits
        4. Apply SemanticDerivations
        5. Create ResultSets

        Args:
            import_process: ImportProcess instance
            raw_dataset: FileAsset instance (RawDataset)
            user: User executing the run

        Returns:
            ImportRun: Execution result

        Raises:
            ImportProcessError: If execution fails
        """
        from datalab.core.models import ImportRun, ResultSet
        from django.core.files.storage import default_storage

        try:
            # Step 1: Inspect shape of the raw dataset
            with default_storage.open(raw_dataset.storage_key, 'rb') as file_obj:
                detected_shape = self.shape_inspector.inspect(
                    file_obj,
                    import_process.file_type,
                    raw_dataset.filename
                )

            # Step 2: Validate shape match (fail-fast)
            shape_match = self.shape_inspector.validate_shape_match(
                detected_shape,
                import_process.shape_fingerprint
            )

            if shape_match['status'] == 'fail':
                # Create failed ImportRun with shape mismatch error
                error_msg = f"Shape mismatch: {', '.join(shape_match.get('reasons', ['Unknown reason']))}"
                import_run = ImportRun.objects.create(
                    tenant=import_process.tenant,
                    import_process=import_process,
                    raw_dataset=raw_dataset,
                    shape_match=shape_match,
                    status='failed',
                    error_message=error_msg
                )
                return import_run

            # Step 3: Extract StructuralUnits (simplified for now)
            if import_process.import_data_as_json:
                with default_storage.open(raw_dataset.storage_key, 'rb') as file_obj:
                    json_data = self._extract_json_object(import_process, file_obj)
                rs = self._create_json_resultset(
                    json_data,
                    import_process=import_process,
                    raw_dataset=raw_dataset,
                    user=user
                )
                resultsets = [rs]
            else:
                extracted_data = self._extract_structural_units(import_process, raw_dataset)
                resultsets = self._apply_semantic_derivations(import_process, extracted_data, user)

            # Step 5: Create successful ImportRun
            import_run = ImportRun.objects.create(
                tenant=import_process.tenant,
                import_process=import_process,
                raw_dataset=raw_dataset,
                shape_match=shape_match,
                status='success',
                resultset_ids=[str(rs.id) for rs in resultsets]
            )

            return import_run

        except Exception as e:
            logger.error(f"ImportProcess execution failed: {e}", exc_info=True)
            # Create failed ImportRun with error details
            error_msg = str(e)
            import_run = ImportRun.objects.create(
                tenant=import_process.tenant,
                import_process=import_process,
                raw_dataset=raw_dataset,
                shape_match={'status': 'error', 'reasons': [error_msg]},
                status='failed',
                error_message=error_msg
            )
            return import_run

    def clone_import_process(self, import_process, new_name: str = None, user=None):
        """
        Clone an ImportProcess to create a new version.

        Args:
            import_process: ImportProcess to clone
            new_name: Optional new name (defaults to "{original} (Copy)")
            user: User performing the clone

        Returns:
            ImportProcess: New cloned process
        """
        new_name = new_name or f"{import_process.name} (Copy)"

        return self.create_import_process(
            tenant=import_process.tenant,
            name=new_name,
            file_type=import_process.file_type,
            shape_fingerprint=import_process.shape_fingerprint,
            shape_description=import_process.shape_description,
            structural_units=import_process.structural_units,
            semantic_derivations=import_process.semantic_derivations,
            user=user
        )

    def execute_legacy_import(
        self,
        source: dict,
        contract_json: dict,
        materialize: bool = False,
        rebuild: bool = False,
        accumulation: dict = None,
        user=None,
        import_data_as_json: bool = False
    ):
        """
        Backward compatibility bridge for /imports/execute/.

        Creates ephemeral ImportProcess and single ImportRun,
        preserving existing behavior.

        Args:
            Same as ImportExecutor.execute()

        Returns:
            ResultSet: Same as before
        """
        # Create ephemeral ImportProcess from contract
        ephemeral_process = self._create_ephemeral_process_from_contract(
            source, contract_json, user, import_data_as_json=import_data_as_json
        )

        # Execute as ImportRun
        import_run = self.run_import_process(ephemeral_process, ephemeral_process.raw_dataset, user)

        if import_run.status == 'failed':
            raise ImportProcessError(f"Shape validation failed: {import_run.shape_match['reasons']}")

        # Return the first (and likely only) ResultSet
        from datalab.core.models import ResultSet
        resultset = ResultSet.objects.get(id=import_run.resultset_ids[0])
        return resultset

    def _extract_structural_units(self, import_process, raw_dataset):
        """
        Extract StructuralUnits from RawDataset using contract_json parser config.
        """
        contract = import_process.contract_json or {}
        parser_config = contract.get('parser', {})
        
        with default_storage.open(raw_dataset.storage_key, 'rb') as file_obj:
            if import_process.file_type == 'csv':
                df = self.import_executor.parser.parse_csv(
                    file_obj,
                    header_row=parser_config.get('header_row', 0),
                    skip_rows=parser_config.get('skip_rows', 0),
                    delimiter=parser_config.get('delimiter', ','),
                    encoding=parser_config.get('encoding')
                )
            elif import_process.file_type == 'excel':
                df = self.import_executor.parser.parse_excel(
                    file_obj,
                    sheet=parser_config.get('sheet', 0),
                    header_row=parser_config.get('header_row', 0),
                    skip_rows=parser_config.get('skip_rows', 0),
                    range_config=parser_config.get('range')
                )
            elif import_process.file_type == 'pdf':
                structural_unit = parser_config.get('structural_unit')
                df = self.import_executor.parser.parse_pdf(file_obj, structural_unit)
            else:
                raise ImportProcessError(f"Unsupported file type: {import_process.file_type}")

        return {'main_data': df}

    def _extract_json_object(self, import_process, file_obj) -> dict[str, Any]:
        """Extract file into a JSON Object without mapping/dedupe."""
        if import_process.file_type == 'pdf':
            structural_unit = {}
            return self.import_executor.pdf_extractor.extract_pdf_as_json(
                file_obj,
                structural_unit=structural_unit
            )
        elif import_process.file_type in ['csv', 'excel']:
            if import_process.file_type == 'csv':
                df = self.import_executor.parser.parse_csv(file_obj)
            else:
                df = self.import_executor.parser.parse_excel(file_obj)
            return self.import_executor._dataframe_to_json_object(df, {'parser': {'type': import_process.file_type}})
        else:
            raise ImportProcessError(f"Unsupported file type for JSON Object import: {import_process.file_type}")

    def _create_json_resultset(self, json_obj: Any, import_process, raw_dataset, user=None) -> ResultSet:
        """Create a ResultSet storing a JSON Object."""
        from datalab.core.models import ResultSet, ResultSetOrigin
        row_count = self.import_executor._compute_row_count_from_json(json_obj, import_process.file_type)
        return ResultSet.objects.create(
            tenant=import_process.tenant,
            name=f"{import_process.name} - JSON",
            origin=ResultSetOrigin.IMPORT,
            schema_json={"type": "json_object", "file_type": import_process.file_type},
            row_count=row_count,
            storage=ResultSetStorage.MEMORY,
            preview_json=serialize_for_json(json_obj),
            lineage_json={
                'import_process_id': str(import_process.id),
                'raw_dataset_id': str(raw_dataset.id),
                'file_type': import_process.file_type
            },
            is_json_object=True,
            created_by=user
        )

    def _apply_semantic_derivations(self, import_process, extracted_data, user):
        """
        Apply contract mapping to create ResultSets.
        
        Uses import_process.contract_json for mapping and type conversion.
        """
        from datalab.core.models import ResultSet, ResultSetOrigin

        df = extracted_data['main_data']
        contract = import_process.contract_json or {}
        
        # Apply contract mapping if defined
        if contract.get('mapping'):
            df = self.import_executor._apply_contract(df, contract)
        
        # Detect schema from transformed data
        schema = self.import_executor.parser.detect_schema(df)

        resultset = ResultSet.objects.create(
            tenant=import_process.tenant,
            name=f"{import_process.name} - Import",
            origin=ResultSetOrigin.IMPORT,
            schema_json=schema,
            row_count=len(df),
            storage=ResultSetStorage.MEMORY,
            lineage_json={
                'import_process_id': str(import_process.id),
                'import_process_version': import_process.version,
                'source': import_process.file_type,
                'contract_version': contract.get('version', '1')
            },
            created_by=user
        )

        # Store preview
        preview_df = df.head(200)
        preview_dict = preview_df.to_dict(orient='records')
        resultset.preview_json = serialize_for_json(preview_dict)
        resultset.save()

        return [resultset]

    def _extract_pdf_data(self, raw_dataset):
        """
        Extract data from PDF file.

        TODO: Implement proper PDF data extraction.
        """
        # Placeholder: return empty DataFrame
        import pandas as pd
        return pd.DataFrame()

    def _create_ephemeral_process_from_contract(self, source, contract_json, user, import_data_as_json: bool = False):
        """
        Create ephemeral ImportProcess from legacy contract for backward compatibility.
        """
        from datalab.core.models import ImportProcess

        # Get tenant and raw dataset
        if 'fileset_id' in source:
            from datalab.core.models import FileSet
            fileset = FileSet.objects.get(id=source['fileset_id'])
            tenant = fileset.tenant
            # Use first file as representative
            raw_dataset = fileset.files.first()
        elif 'file_id' in source:
            raw_dataset = FileAsset.objects.get(id=source['file_id'])
            tenant = raw_dataset.tenant
        else:
            raise ImportProcessError("Invalid source")

        # Inspect shape to get fingerprint
        with default_storage.open(raw_dataset.storage_key, 'rb') as file_obj:
            shape_info = self.shape_inspector.inspect(
                file_obj,
                contract_json.get('parser', {}).get('type', 'csv'),
                raw_dataset.filename
            )

        # Create ephemeral process (not saved to DB)
        process = ImportProcess(
            tenant=tenant,
            name=f"Ephemeral Import - {raw_dataset.filename}",
            file_type=contract_json.get('parser', {}).get('type', 'csv'),
            shape_fingerprint=shape_info['fingerprint'],
            shape_description=shape_info['description'],
            structural_units=[],  # Ephemeral
            semantic_derivations=[],  # Ephemeral
            version=1,
            is_active=True,
            import_data_as_json=import_data_as_json
        )

        # Attach raw_dataset for later use
        process.raw_dataset = raw_dataset

        return process


class ImportProcessError(Exception):
    """Raised when ImportProcess operations fail."""
    pass
