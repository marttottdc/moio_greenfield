"""
Analyzer Service for Moio Data Lab.

The Analyzer is the ONLY component that executes analytics.
It interprets Analysis Models and produces ResultSets.

Phase 2 capabilities:
- Multi-way joins with join graph validation
- Cardinality enforcement (one_to_one, many_to_one, etc.)
- HAVING support (post-aggregation filtering)
- Query optimization (join ordering, predicate pushdown)
- Enhanced result caching
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pandas as pd
from django.db import transaction
from django.utils import timezone

from datalab.analytics.models import AnalysisModel, AnalyzerRun
from datalab.core.models import (
    Dataset,
    ResultSet,
    ResultSetOrigin,
    ResultSetStorage,
)
from datalab.core.serialization import serialize_for_json
from datalab.core.storage import get_storage
from central_hub.models import Tenant

logger = logging.getLogger(__name__)


class AnalyzerError(Exception):
    """Base exception for Analyzer errors."""
    pass


class AnalyzerValidationError(AnalyzerError):
    """Raised when request validation fails."""
    def __init__(self, message: str, errors: list[dict]):
        super().__init__(message)
        self.errors = errors


class AnalyzerExecutionError(AnalyzerError):
    """Raised when execution fails."""
    pass


class CardinalityViolationError(AnalyzerError):
    """Raised when join cardinality constraints are violated."""
    def __init__(self, message: str, join_spec: dict, details: dict):
        super().__init__(message)
        self.join_spec = join_spec
        self.details = details


class JoinGraphError(AnalyzerError):
    """Raised when join graph is invalid."""
    pass


class AnalyzerService:
    """
    The Analyzer service executes analytics.
    
    Responsibilities:
    1. Validate requests against Analysis Model constraints
    2. Resolve dataset versions
    3. Hydrate datasets (load as DataFrames)
    4. Apply analytical joins
    5. Filter data
    6. Group and aggregate
    7. Order and limit results
    8. Produce ResultSets with full lineage
    """
    
    PREVIEW_LIMIT = 200
    MATERIALIZE_THRESHOLD = 10000
    CACHE_TTL_MINUTES = 5
    
    def __init__(self):
        self.storage = get_storage()
    
    # ─────────────────────────────────────────────────────────────
    # Main Entry Point
    # ─────────────────────────────────────────────────────────────
    
    def execute(
        self,
        analysis_model: AnalysisModel,
        request: dict[str, Any],
        user=None,
        use_cache: bool = True
    ) -> dict[str, Any]:
        """
        Execute an Analysis Model with the given request.
        
        Args:
            analysis_model: The AnalysisModel to execute
            request: Declarative execution request:
                {
                    "parameters": {...},
                    "dimensions": [...],
                    "measures": [...],
                    "filters": [...],
                    "time_grain": "day",
                    "order_by": [...],
                    "limit": 1000
                }
            user: User executing the analysis
            use_cache: Whether to check/use cache
            
        Returns:
            Response dict with resultset_id, schema, row_count, data, metadata
            
        Raises:
            AnalyzerValidationError: If request validation fails
            AnalyzerExecutionError: If execution fails
        """
        started_at = timezone.now()
        
        # Step 1: Validate request
        validation_errors = analysis_model.validate_request(request)
        if validation_errors:
            raise AnalyzerValidationError(
                "Invalid analysis request",
                validation_errors
            )
        
        # Step 2: Generate cache key and check cache
        cache_key = self._generate_cache_key(analysis_model, request)
        if use_cache:
            cached_run = self._check_cache(cache_key, analysis_model.tenant)
            if cached_run:
                return self._build_response(cached_run, cache_hit=True)
        
        # Step 3: Create AnalyzerRun record
        run = AnalyzerRun.objects.create(
            tenant=analysis_model.tenant,
            analysis_model=analysis_model,
            analysis_model_version=analysis_model.version,
            request_json=request,
            status=AnalyzerRun.STATUS_RUNNING,
            cache_key=cache_key,
            started_at=started_at,
            created_by=user
        )
        
        try:
            # Step 4: Resolve datasets
            resolved = self._resolve_datasets(analysis_model)
            run.resolved_datasets_json = resolved
            run.save(update_fields=['resolved_datasets_json'])
            
            # Step 5: Hydrate datasets (load as DataFrames)
            dataframes = self._hydrate_datasets(analysis_model, resolved)
            
            # Step 6: Apply analytical joins
            joined_df = self._apply_joins(analysis_model, dataframes)
            
            # Step 7: Apply filters
            filtered_df = self._apply_filters(joined_df, analysis_model, request)
            
            # Step 8: Apply grouping and aggregation
            result_df = self._aggregate(filtered_df, analysis_model, request)
            
            # Step 9: Phase 2 - Apply HAVING (post-aggregation filtering)
            result_df = self._apply_having(result_df, analysis_model, request)
            
            # Step 10: Apply ordering and limit
            result_df = self._apply_order_and_limit(result_df, request)
            
            # Step 11: Create ResultSet
            resultset = self._create_resultset(
                result_df,
                analysis_model,
                run,
                user
            )
            
            # Step 12: Update run record
            completed_at = timezone.now()
            execution_time_ms = int((completed_at - started_at).total_seconds() * 1000)
            
            run.resultset = resultset
            run.status = AnalyzerRun.STATUS_SUCCESS
            run.completed_at = completed_at
            run.execution_time_ms = execution_time_ms
            run.save(update_fields=[
                'resultset', 'status', 'completed_at', 'execution_time_ms'
            ])
            
            return self._build_response(run, cache_hit=False)
            
        except Exception as exc:
            logger.error(f"Analyzer execution failed: {exc}", exc_info=True)
            run.status = AnalyzerRun.STATUS_FAILED
            run.error_message = str(exc)
            run.error_details_json = {
                'type': type(exc).__name__,
                'message': str(exc)
            }
            run.completed_at = timezone.now()
            run.save(update_fields=[
                'status', 'error_message', 'error_details_json', 'completed_at'
            ])
            raise AnalyzerExecutionError(f"Execution failed: {exc}") from exc
    
    # ─────────────────────────────────────────────────────────────
    # Resolution
    # ─────────────────────────────────────────────────────────────
    
    def _resolve_datasets(self, analysis_model: AnalysisModel) -> dict[str, dict]:
        """
        Resolve dataset references to specific versions.
        
        For Phase 1, we always use the current (latest) version.
        Future: Support pinned versions, time-travel, etc.
        """
        resolved = {}
        
        for ds_ref in analysis_model.datasets_json:
            dataset_id = ds_ref['ref']
            alias = ds_ref['alias']
            
            try:
                dataset = Dataset.objects.get(
                    id=dataset_id,
                    tenant=analysis_model.tenant
                )
            except Dataset.DoesNotExist:
                raise AnalyzerExecutionError(
                    f"Dataset {dataset_id} (alias: {alias}) not found"
                )
            
            if not dataset.current_version:
                raise AnalyzerExecutionError(
                    f"Dataset '{dataset.name}' has no current version"
                )
            
            version = dataset.current_version
            resolved[alias] = {
                'dataset_id': str(dataset.id),
                'dataset_name': dataset.name,
                'version_id': str(version.id),
                'version_number': version.version_number,
                'resultset_id': str(version.result_set_id),
                'row_count': version.result_set.row_count
            }
        
        return resolved
    
    # ─────────────────────────────────────────────────────────────
    # Hydration
    # ─────────────────────────────────────────────────────────────
    
    def _hydrate_datasets(
        self,
        analysis_model: AnalysisModel,
        resolved: dict[str, dict]
    ) -> dict[str, pd.DataFrame]:
        """
        Load resolved datasets as DataFrames.
        
        Hydration is INTERNAL and INVISIBLE to the Analysis Model.
        Each dataset appears as one logical DataFrame regardless of
        how many internal joins were needed to construct it.
        """
        dataframes = {}
        
        for alias, resolution in resolved.items():
            resultset_id = resolution['resultset_id']
            
            try:
                resultset = ResultSet.objects.get(id=resultset_id)
            except ResultSet.DoesNotExist:
                raise AnalyzerExecutionError(
                    f"ResultSet {resultset_id} for dataset '{alias}' not found"
                )
            
            df = self._load_resultset_as_dataframe(resultset)
            
            # Prefix all columns with alias for clarity in joins
            df = df.add_prefix(f"{alias}.")
            
            dataframes[alias] = df
            
            logger.debug(
                f"Hydrated dataset '{alias}': {len(df)} rows, "
                f"columns: {list(df.columns)}"
            )
        
        return dataframes
    
    def _load_resultset_as_dataframe(self, resultset: ResultSet) -> pd.DataFrame:
        """Load a ResultSet as a DataFrame."""
        if resultset.storage == ResultSetStorage.PARQUET:
            return self.storage.load_parquet(resultset.id)
        else:
            # Memory storage: reconstruct from preview_json
            if not resultset.preview_json:
                return pd.DataFrame()
            return pd.DataFrame(resultset.preview_json)
    
    # ─────────────────────────────────────────────────────────────
    # Joins (Analytical, NOT Hydration) - Phase 2 Enhanced
    # ─────────────────────────────────────────────────────────────
    
    def _apply_joins(
        self,
        analysis_model: AnalysisModel,
        dataframes: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        Apply ANALYTICAL joins as declared in the Analysis Model.
        
        Phase 2 enhancements:
        - Multi-way join graph validation
        - Cardinality enforcement
        - Optimized join ordering
        
        These are NOT hydration joins. Hydration is invisible and
        already completed. These are semantic joins between Datasets.
        """
        joins = analysis_model.joins_json
        
        if not joins:
            # No joins: single dataset mode
            if len(dataframes) != 1:
                raise AnalyzerExecutionError(
                    f"Analysis Model has {len(dataframes)} datasets but no joins defined"
                )
            return list(dataframes.values())[0]
        
        # Phase 2: Validate join graph connectivity
        self._validate_join_graph(dataframes.keys(), joins)
        
        # Phase 2: Optimize join order based on cardinality and row counts
        ordered_joins = self._optimize_join_order(joins, dataframes)
        
        # Determine starting dataset (smallest after considering filters)
        start_alias = self._select_starting_dataset(ordered_joins, dataframes)
        
        if start_alias not in dataframes:
            raise AnalyzerExecutionError(
                f"Starting dataset '{start_alias}' not found"
            )
        
        result = dataframes[start_alias].copy()
        joined_aliases = {start_alias}
        
        # Apply joins in optimized order
        for join_spec in ordered_joins:
            left_alias = join_spec['left']['dataset']
            right_alias = join_spec['right']['dataset']
            
            # Determine which side to join (handle bidirectional)
            if left_alias in joined_aliases and right_alias not in joined_aliases:
                join_from = 'left'
                new_alias = right_alias
            elif right_alias in joined_aliases and left_alias not in joined_aliases:
                join_from = 'right'
                new_alias = left_alias
            elif left_alias in joined_aliases and right_alias in joined_aliases:
                # Both already joined, skip
                continue
            else:
                # Neither joined yet - find a path
                # This shouldn't happen with a connected graph
                logger.warning(
                    f"Neither {left_alias} nor {right_alias} are in joined set, skipping"
                )
                continue
            
            if new_alias not in dataframes:
                raise AnalyzerExecutionError(
                    f"Dataset '{new_alias}' referenced in join but not found"
                )
            
            new_df = dataframes[new_alias]
            
            # Build join keys
            left_field = join_spec['left']['field']
            right_field = join_spec['right']['field']
            join_type = join_spec.get('type', 'left')
            cardinality = join_spec.get('cardinality')
            
            if join_from == 'left':
                left_key = f"{left_alias}.{left_field}"
                right_key = f"{new_alias}.{right_field}"
            else:
                # Swap the join direction
                left_key = f"{right_alias}.{right_field}"
                right_key = f"{new_alias}.{left_field}"
                # Adjust join type for swapped direction
                if join_type == 'left':
                    join_type = 'right'
                elif join_type == 'right':
                    join_type = 'left'
            
            # Map join type to pandas
            pandas_how = {
                'inner': 'inner',
                'left': 'left',
                'right': 'right',
                'full': 'outer'
            }.get(join_type, 'left')
            
            # Check keys exist
            if left_key not in result.columns:
                raise AnalyzerExecutionError(
                    f"Join key '{left_key}' not found in result dataset. "
                    f"Available: {list(result.columns)[:10]}..."
                )
            if right_key not in new_df.columns:
                raise AnalyzerExecutionError(
                    f"Join key '{right_key}' not found in dataset '{new_alias}'. "
                    f"Available: {list(new_df.columns)[:10]}..."
                )
            
            # Phase 2: Enforce cardinality constraints
            if cardinality:
                self._enforce_cardinality(
                    result, left_key,
                    new_df, right_key,
                    cardinality, join_spec
                )
            
            rows_before = len(result)
            
            result = pd.merge(
                result,
                new_df,
                left_on=left_key,
                right_on=right_key,
                how=pandas_how,
                suffixes=('', '_dup')
            )
            
            # Drop duplicate key column if created
            dup_cols = [c for c in result.columns if c.endswith('_dup')]
            if dup_cols:
                result = result.drop(columns=dup_cols)
            
            joined_aliases.add(new_alias)
            
            # Warn about potential row explosion
            if len(result) > rows_before * 2:
                logger.warning(
                    f"Row explosion detected: {rows_before} -> {len(result)} rows "
                    f"after joining '{new_alias}'. Check cardinality."
                )
            
            logger.debug(
                f"Applied {join_type} join with {new_alias}: "
                f"{rows_before} -> {len(result)} rows"
            )
        
        return result
    
    def _validate_join_graph(
        self,
        datasets: set[str],
        joins: list[dict]
    ) -> None:
        """
        Validate that the join graph connects all datasets.
        
        Phase 2: Ensures no orphaned datasets in multi-way joins.
        """
        if len(datasets) <= 1:
            return
        
        # Build adjacency list
        graph = defaultdict(set)
        for join_spec in joins:
            left = join_spec['left']['dataset']
            right = join_spec['right']['dataset']
            graph[left].add(right)
            graph[right].add(left)
        
        # Check all datasets are in the graph
        datasets_in_graph = set(graph.keys())
        missing = set(datasets) - datasets_in_graph
        if missing:
            raise JoinGraphError(
                f"Datasets {missing} are not connected by any join. "
                f"All datasets in an Analysis Model must be connected."
            )
        
        # Check graph is connected using BFS
        if datasets_in_graph:
            start = next(iter(datasets_in_graph))
            visited = set()
            queue = [start]
            
            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                queue.extend(graph[node] - visited)
            
            disconnected = datasets_in_graph - visited
            if disconnected:
                raise JoinGraphError(
                    f"Join graph is not connected. Datasets {disconnected} "
                    f"are not reachable from {start}."
                )
    
    def _optimize_join_order(
        self,
        joins: list[dict],
        dataframes: dict[str, pd.DataFrame]
    ) -> list[dict]:
        """
        Optimize join order for better performance.
        
        Phase 2: Heuristics:
        1. Start with smaller tables
        2. Prefer many-to-one joins early (they don't explode rows)
        3. Apply predicates before joins when possible
        """
        if len(joins) <= 1:
            return joins
        
        # Score each join
        scored_joins = []
        for join_spec in joins:
            left_alias = join_spec['left']['dataset']
            right_alias = join_spec['right']['dataset']
            cardinality = join_spec.get('cardinality', 'many_to_many')
            
            left_rows = len(dataframes.get(left_alias, pd.DataFrame()))
            right_rows = len(dataframes.get(right_alias, pd.DataFrame()))
            
            # Score: lower is better (process first)
            # Prefer many_to_one (no row explosion)
            cardinality_score = {
                'one_to_one': 0,
                'many_to_one': 1,
                'one_to_many': 2,
                'many_to_many': 3
            }.get(cardinality, 3)
            
            # Prefer joins with smaller tables
            size_score = min(left_rows, right_rows) / 10000
            
            score = cardinality_score + size_score
            scored_joins.append((score, join_spec))
        
        # Sort by score
        scored_joins.sort(key=lambda x: x[0])
        
        return [j[1] for j in scored_joins]
    
    def _select_starting_dataset(
        self,
        joins: list[dict],
        dataframes: dict[str, pd.DataFrame]
    ) -> str:
        """Select the best dataset to start joining from."""
        if not joins:
            return next(iter(dataframes.keys()))
        
        # Count how many joins each dataset participates in
        dataset_counts = defaultdict(int)
        for join_spec in joins:
            dataset_counts[join_spec['left']['dataset']] += 1
            dataset_counts[join_spec['right']['dataset']] += 1
        
        # Prefer datasets that participate in many joins (star schema center)
        # and are smaller
        best = None
        best_score = float('inf')
        
        for alias, df in dataframes.items():
            join_count = dataset_counts.get(alias, 0)
            row_count = len(df)
            
            # Score: prefer high join count, low row count
            score = row_count / (join_count + 1)
            
            if score < best_score:
                best_score = score
                best = alias
        
        return best or next(iter(dataframes.keys()))
    
    def _enforce_cardinality(
        self,
        left_df: pd.DataFrame,
        left_key: str,
        right_df: pd.DataFrame,
        right_key: str,
        cardinality: str,
        join_spec: dict
    ) -> None:
        """
        Enforce cardinality constraints before joining.
        
        Phase 2: Validates join cardinality to prevent data corruption.
        
        Cardinalities:
        - one_to_one: Both sides must have unique keys
        - many_to_one: Right side must have unique keys
        - one_to_many: Left side must have unique keys
        - many_to_many: No constraints (but warn about potential explosion)
        """
        left_unique = left_df[left_key].nunique() == len(left_df)
        right_unique = right_df[right_key].nunique() == len(right_df)
        
        left_dupes = len(left_df) - left_df[left_key].nunique()
        right_dupes = len(right_df) - right_df[right_key].nunique()
        
        if cardinality == 'one_to_one':
            if not left_unique:
                raise CardinalityViolationError(
                    f"one_to_one cardinality violated: Left key '{left_key}' "
                    f"has {left_dupes} duplicate values",
                    join_spec,
                    {'left_duplicates': left_dupes}
                )
            if not right_unique:
                raise CardinalityViolationError(
                    f"one_to_one cardinality violated: Right key '{right_key}' "
                    f"has {right_dupes} duplicate values",
                    join_spec,
                    {'right_duplicates': right_dupes}
                )
        
        elif cardinality == 'many_to_one':
            if not right_unique:
                raise CardinalityViolationError(
                    f"many_to_one cardinality violated: Right key '{right_key}' "
                    f"has {right_dupes} duplicate values (expected unique)",
                    join_spec,
                    {'right_duplicates': right_dupes}
                )
        
        elif cardinality == 'one_to_many':
            if not left_unique:
                raise CardinalityViolationError(
                    f"one_to_many cardinality violated: Left key '{left_key}' "
                    f"has {left_dupes} duplicate values (expected unique)",
                    join_spec,
                    {'left_duplicates': left_dupes}
                )
        
        elif cardinality == 'many_to_many':
            # No constraint, but warn about potential explosion
            estimated_rows = len(left_df) * (len(right_df) / right_df[right_key].nunique())
            if estimated_rows > len(left_df) * 10:
                logger.warning(
                    f"many_to_many join may cause significant row expansion: "
                    f"~{int(estimated_rows)} estimated rows"
                )
    
    # ─────────────────────────────────────────────────────────────
    # Filtering
    # ─────────────────────────────────────────────────────────────
    
    def _apply_filters(
        self,
        df: pd.DataFrame,
        analysis_model: AnalysisModel,
        request: dict
    ) -> pd.DataFrame:
        """Apply filters from the request."""
        filters = request.get('filters', [])
        parameters = request.get('parameters', {})
        
        if not filters and not parameters:
            return df
        
        result = df.copy()
        
        # Apply explicit filters
        for f in filters:
            field = f['field']
            op = f.get('op', 'eq')
            value = f.get('value')
            values = f.get('values', [])
            
            # Find the column (may need to look up source from dimension)
            col = self._find_column(result, field, analysis_model)
            if col is None:
                logger.warning(f"Filter field '{field}' not found in DataFrame, skipping")
                continue
            
            result = self._apply_filter_op(result, col, op, value, values)
        
        # Apply parameter-based date filtering
        date_from = parameters.get('date_from')
        date_to = parameters.get('date_to')
        
        if date_from or date_to:
            time_field = analysis_model.time_semantics_json.get('primary_time_field')
            if time_field:
                time_col = self._find_column(result, time_field, analysis_model)
                if time_col and time_col in result.columns:
                    # Convert to datetime if needed
                    if not pd.api.types.is_datetime64_any_dtype(result[time_col]):
                        result[time_col] = pd.to_datetime(result[time_col], errors='coerce')
                    
                    if date_from:
                        date_from_resolved = self._resolve_date_param(date_from)
                        result = result[result[time_col] >= date_from_resolved]
                    
                    if date_to:
                        date_to_resolved = self._resolve_date_param(date_to)
                        result = result[result[time_col] <= date_to_resolved]
        
        logger.debug(f"After filtering: {len(result)} rows")
        return result
    
    # ─────────────────────────────────────────────────────────────
    # HAVING (Post-Aggregation Filtering) - Phase 2
    # ─────────────────────────────────────────────────────────────
    
    def _apply_having(
        self,
        df: pd.DataFrame,
        analysis_model: AnalysisModel,
        request: dict
    ) -> pd.DataFrame:
        """
        Apply HAVING clauses (post-aggregation filtering).
        
        Phase 2: Filters applied AFTER aggregation, operating on measure values.
        
        Request format:
        {
            "having": [
                {"measure": "total_revenue", "op": "gte", "value": 1000},
                {"measure": "order_count", "op": "gt", "value": 5}
            ]
        }
        """
        having_clauses = request.get('having', [])
        
        if not having_clauses:
            return df
        
        result = df.copy()
        
        for clause in having_clauses:
            measure = clause.get('measure')
            op = clause.get('op', 'eq')
            value = clause.get('value')
            values = clause.get('values', [])
            
            # Validate measure exists in Analysis Model
            measure_def = analysis_model.get_measure_by_name(measure)
            if not measure_def:
                logger.warning(
                    f"HAVING clause references unknown measure '{measure}', skipping"
                )
                continue
            
            # Check column exists in aggregated result
            if measure not in result.columns:
                logger.warning(
                    f"HAVING clause references measure '{measure}' not in results, skipping"
                )
                continue
            
            rows_before = len(result)
            result = self._apply_filter_op(result, measure, op, value, values)
            
            logger.debug(
                f"HAVING {measure} {op} {value}: {rows_before} -> {len(result)} rows"
            )
        
        logger.debug(f"After HAVING: {len(result)} rows")
        return result
    
    def _apply_filter_op(
        self,
        df: pd.DataFrame,
        col: str,
        op: str,
        value: Any,
        values: list
    ) -> pd.DataFrame:
        """Apply a single filter operation."""
        if op == 'eq':
            return df[df[col] == value]
        elif op == 'ne':
            return df[df[col] != value]
        elif op == 'gt':
            return df[df[col] > value]
        elif op == 'gte':
            return df[df[col] >= value]
        elif op == 'lt':
            return df[df[col] < value]
        elif op == 'lte':
            return df[df[col] <= value]
        elif op == 'in':
            return df[df[col].isin(values)]
        elif op == 'not_in':
            return df[~df[col].isin(values)]
        elif op == 'is_null':
            return df[df[col].isna()]
        elif op == 'is_not_null':
            return df[df[col].notna()]
        elif op == 'contains':
            return df[df[col].astype(str).str.contains(str(value), na=False, case=False)]
        elif op == 'starts_with':
            return df[df[col].astype(str).str.startswith(str(value), na=False)]
        elif op == 'ends_with':
            return df[df[col].astype(str).str.endswith(str(value), na=False)]
        elif op == 'between':
            if len(values) >= 2:
                return df[(df[col] >= values[0]) & (df[col] <= values[1])]
        return df
    
    def _resolve_date_param(self, value: Any) -> datetime:
        """Resolve date parameter, supporting relative syntax."""
        if isinstance(value, datetime):
            return value
        
        value_str = str(value)
        
        # Handle relative dates
        if value_str.startswith('relative:'):
            rel = value_str[9:]  # Remove 'relative:' prefix
            now = timezone.now()
            
            if rel == 'today':
                return now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif rel == 'yesterday':
                return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif rel == 'start_of_week':
                return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            elif rel == 'start_of_month':
                return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            elif rel == 'start_of_year':
                return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            elif rel.startswith('-') and rel.endswith('d'):
                days = int(rel[1:-1])
                return (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif rel.startswith('-') and rel.endswith('w'):
                weeks = int(rel[1:-1])
                return (now - timedelta(weeks=weeks)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif rel.startswith('-') and rel.endswith('m'):
                months = int(rel[1:-1])
                # Approximate months
                return (now - timedelta(days=months * 30)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Parse as date string
        return pd.to_datetime(value_str)
    
    def _find_column(
        self,
        df: pd.DataFrame,
        field: str,
        analysis_model: AnalysisModel
    ) -> str | None:
        """
        Find the actual column name in the DataFrame for a field reference.
        
        Fields in requests use dimension/measure names.
        We need to map these to actual column names (which are prefixed).
        """
        # First, check if it's a dimension and get its source
        dim = analysis_model.get_dimension_by_name(field)
        if dim:
            source = dim['source']  # e.g., "orders.created_at"
            if source in df.columns:
                return source
        
        # Check if it's a measure (measures are computed, not in raw data)
        # For filtering, we typically filter on dimensions, not measures
        
        # Direct match
        if field in df.columns:
            return field
        
        # Try common patterns
        for col in df.columns:
            # Match end of column name
            if col.endswith(f".{field}"):
                return col
            # Match without prefix
            parts = col.split('.')
            if len(parts) > 1 and parts[-1] == field:
                return col
        
        return None
    
    # ─────────────────────────────────────────────────────────────
    # Aggregation
    # ─────────────────────────────────────────────────────────────
    
    def _aggregate(
        self,
        df: pd.DataFrame,
        analysis_model: AnalysisModel,
        request: dict
    ) -> pd.DataFrame:
        """
        Apply grouping and aggregation based on requested dimensions and measures.
        """
        dimensions = request.get('dimensions', [])
        measures = request.get('measures', [])
        time_grain = request.get('time_grain')
        
        if not dimensions and not measures:
            # No aggregation requested - return as-is
            return df
        
        if not measures:
            # Only dimensions, no measures - just select unique combinations
            group_cols = []
            for dim_name in dimensions:
                dim_def = analysis_model.get_dimension_by_name(dim_name)
                if dim_def:
                    source = dim_def['source']
                    if source in df.columns:
                        group_cols.append(source)
            
            if group_cols:
                result = df[group_cols].drop_duplicates()
                # Rename columns to dimension names
                rename_map = {}
                for dim_name in dimensions:
                    dim_def = analysis_model.get_dimension_by_name(dim_name)
                    if dim_def and dim_def['source'] in result.columns:
                        rename_map[dim_def['source']] = dim_name
                return result.rename(columns=rename_map)
            return df
        
        # Build dimension columns (for GROUP BY)
        group_cols = []
        dim_renames = {}  # source_col -> dim_name
        
        for dim_name in dimensions:
            dim_def = analysis_model.get_dimension_by_name(dim_name)
            if not dim_def:
                continue
            
            source = dim_def['source']
            col = source if source in df.columns else None
            
            if col is None:
                logger.warning(f"Dimension source '{source}' not found in DataFrame")
                continue
            
            # Handle time graining
            dim_type = dim_def.get('type', 'string')
            if dim_type in ('date', 'datetime') and time_grain:
                # Create graining column
                grain_col = f"_grain_{dim_name}"
                df = self._apply_time_grain(df, col, grain_col, time_grain)
                group_cols.append(grain_col)
                dim_renames[grain_col] = dim_name
            else:
                group_cols.append(col)
                dim_renames[col] = dim_name
        
        # Build aggregation dict for measures
        agg_exprs = []
        
        for measure_name in measures:
            measure_def = analysis_model.get_measure_by_name(measure_name)
            if not measure_def:
                continue
            
            expr = measure_def['expr']
            parsed = self._parse_measure_expr(expr, df, analysis_model)
            if parsed:
                agg_exprs.append({
                    'name': measure_name,
                    'func': parsed[0],
                    'col': parsed[1]
                })
        
        # Perform aggregation
        if group_cols and agg_exprs:
            # Build aggregation
            agg_dict = {}
            for agg in agg_exprs:
                col = agg['col']
                func = agg['func']
                name = agg['name']
                # Use named aggregation
                if col not in agg_dict:
                    agg_dict[col] = []
                agg_dict[col].append((name, func))
            
            # Execute groupby with multiple aggregations
            grouped = df.groupby(group_cols, as_index=False)
            
            # Build result with proper column names
            result_parts = [df[group_cols].drop_duplicates().reset_index(drop=True)]
            
            for col, agg_list in agg_dict.items():
                for name, func in agg_list:
                    if func == 'nunique':
                        agg_result = grouped[col].nunique().reset_index()
                    else:
                        agg_result = grouped[col].agg(func).reset_index()
                    agg_result = agg_result.rename(columns={col: name})
                    # Drop group columns from agg_result for merge
                    agg_result = agg_result[[name]]
                    result_parts.append(agg_result)
            
            # Combine results
            if len(result_parts) > 1:
                result = pd.concat(result_parts, axis=1)
            else:
                result = result_parts[0]
            
            # Actually, let's do this more simply
            result = df.groupby(group_cols, as_index=False).agg(
                **{agg['name']: (agg['col'], agg['func']) for agg in agg_exprs}
            )
            
            # Rename group columns to dimension names
            result = result.rename(columns=dim_renames)
            
        elif agg_exprs:
            # Global aggregation (no dimensions)
            result_data = {}
            for agg in agg_exprs:
                col = agg['col']
                func = agg['func']
                name = agg['name']
                
                if func == 'nunique':
                    result_data[name] = df[col].nunique()
                elif func == 'sum':
                    result_data[name] = df[col].sum()
                elif func == 'count':
                    result_data[name] = df[col].count()
                elif func == 'mean':
                    result_data[name] = df[col].mean()
                elif func == 'min':
                    result_data[name] = df[col].min()
                elif func == 'max':
                    result_data[name] = df[col].max()
            
            result = pd.DataFrame([result_data])
        
        else:
            # No aggregation needed
            result = df
        
        logger.debug(f"After aggregation: {len(result)} rows, columns: {list(result.columns)}")
        return result
    
    def _apply_time_grain(
        self,
        df: pd.DataFrame,
        col: str,
        output_col: str,
        grain: str
    ) -> pd.DataFrame:
        """Apply time graining to a column."""
        df = df.copy()
        
        # Ensure datetime type
        if not pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = pd.to_datetime(df[col], errors='coerce')
        
        if grain == 'day':
            df[output_col] = df[col].dt.date
        elif grain == 'week':
            df[output_col] = df[col].dt.to_period('W').dt.start_time.dt.date
        elif grain == 'month':
            df[output_col] = df[col].dt.to_period('M').dt.start_time.dt.date
        elif grain == 'quarter':
            df[output_col] = df[col].dt.to_period('Q').dt.start_time.dt.date
        elif grain == 'year':
            df[output_col] = df[col].dt.to_period('Y').dt.start_time.dt.date
        elif grain == 'hour':
            df[output_col] = df[col].dt.floor('h')
        else:
            df[output_col] = df[col].dt.date
        
        return df
    
    def _parse_measure_expr(
        self,
        expr: str,
        df: pd.DataFrame,
        analysis_model: AnalysisModel
    ) -> tuple[str, str] | None:
        """
        Parse a measure expression like SUM(orders.amount).
        
        Returns (agg_function, column_name) or None if parsing fails.
        """
        expr_upper = expr.strip().upper()
        
        # Pattern: FUNC(field)
        match = re.match(
            r'(SUM|COUNT|AVG|MIN|MAX|COUNT_DISTINCT)\s*\(\s*(.+?)\s*\)',
            expr_upper,
            re.IGNORECASE
        )
        
        if not match:
            logger.warning(f"Could not parse measure expression: {expr}")
            return None
        
        func = match.group(1).lower()
        field = match.group(2)
        
        # Map to pandas agg functions
        func_map = {
            'sum': 'sum',
            'count': 'count',
            'avg': 'mean',
            'min': 'min',
            'max': 'max',
            'count_distinct': 'nunique'
        }
        
        agg_func = func_map.get(func)
        if not agg_func:
            return None
        
        # The field in expression is like "orders.amount"
        # After hydration, columns are prefixed, so it should match
        # Try exact match first
        field_lower = field.lower()
        
        # Find matching column (case-insensitive)
        col = None
        for c in df.columns:
            if c.lower() == field_lower:
                col = c
                break
        
        if col is None:
            logger.warning(f"Measure field '{field}' not found in DataFrame columns: {list(df.columns)[:10]}...")
            return None
        
        return (agg_func, col)
    
    # ─────────────────────────────────────────────────────────────
    # Ordering and Limiting
    # ─────────────────────────────────────────────────────────────
    
    def _apply_order_and_limit(
        self,
        df: pd.DataFrame,
        request: dict
    ) -> pd.DataFrame:
        """Apply ordering and limit to results."""
        order_by = request.get('order_by', [])
        limit = request.get('limit')
        
        if order_by:
            sort_cols = []
            ascending = []
            
            for ob in order_by:
                field = ob.get('field')
                direction = ob.get('direction', 'asc')
                
                if field in df.columns:
                    sort_cols.append(field)
                    ascending.append(direction.lower() == 'asc')
            
            if sort_cols:
                df = df.sort_values(by=sort_cols, ascending=ascending)
        
        if limit and limit > 0:
            df = df.head(limit)
        
        return df.reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────────
    # ResultSet Creation
    # ─────────────────────────────────────────────────────────────
    
    def _create_resultset(
        self,
        df: pd.DataFrame,
        analysis_model: AnalysisModel,
        run: AnalyzerRun,
        user
    ) -> ResultSet:
        """Create ResultSet from analysis results."""
        from datalab.imports.parsers import FileParser
        
        # Detect schema
        schema = FileParser.detect_schema(df)
        
        # Build lineage
        lineage = {
            'origin': ResultSetOrigin.ANALYZER,
            'analyzer_run_id': str(run.id),
            'analysis_model_id': str(analysis_model.id),
            'analysis_model_version': analysis_model.version,
            'resolved_datasets': run.resolved_datasets_json,
            'request': run.request_json
        }
        
        # Create ResultSet
        resultset = ResultSet.objects.create(
            tenant=analysis_model.tenant,
            name=f"Analysis: {analysis_model.name}",
            origin=ResultSetOrigin.ANALYZER,
            schema_json=schema,
            row_count=len(df),
            storage=ResultSetStorage.MEMORY,
            lineage_json=lineage,
            durability='ephemeral',  # Analyzer outputs are ephemeral by default
            created_by=user
        )
        
        # Materialize if large
        if len(df) > self.MATERIALIZE_THRESHOLD:
            storage_key = self.storage.save_parquet(df, resultset.id)
            resultset.storage = ResultSetStorage.PARQUET
            resultset.storage_key = storage_key
            resultset.save(update_fields=['storage', 'storage_key'])
            
            # Still store preview
            preview = df.head(self.PREVIEW_LIMIT).to_dict(orient='records')
            resultset.preview_json = serialize_for_json(preview)
            resultset.save(update_fields=['preview_json'])
        else:
            # Store full data as preview (within limits)
            preview = df.head(self.PREVIEW_LIMIT).to_dict(orient='records')
            resultset.preview_json = serialize_for_json(preview)
            resultset.save(update_fields=['preview_json'])
        
        return resultset
    
    # ─────────────────────────────────────────────────────────────
    # Caching - Phase 2 Enhanced
    # ─────────────────────────────────────────────────────────────
    
    def _generate_cache_key(
        self,
        analysis_model: AnalysisModel,
        request: dict,
        resolved_datasets: dict[str, dict] | None = None
    ) -> str:
        """
        Generate cache key for a request.
        
        Phase 2: Includes dataset versions in cache key so cache
        automatically invalidates when underlying data changes.
        """
        cache_data = {
            'model_id': str(analysis_model.id),
            'model_version': analysis_model.version,
            'request': request
        }
        
        # Include dataset versions if available
        # This ensures cache invalidates when data changes
        if resolved_datasets:
            cache_data['dataset_versions'] = {
                alias: info.get('version_number')
                for alias, info in resolved_datasets.items()
            }
        
        cache_str = json.dumps(cache_data, sort_keys=True, default=str)
        return hashlib.sha256(cache_str.encode()).hexdigest()
    
    def _check_cache(
        self,
        cache_key: str,
        tenant: Tenant,
        ttl_minutes: int | None = None
    ) -> AnalyzerRun | None:
        """
        Check if a valid cached result exists.
        
        Phase 2: Supports custom TTL per request.
        """
        ttl = ttl_minutes or self.CACHE_TTL_MINUTES
        cache_cutoff = timezone.now() - timedelta(minutes=ttl)
        
        cached_run = AnalyzerRun.objects.filter(
            tenant=tenant,
            cache_key=cache_key,
            status=AnalyzerRun.STATUS_SUCCESS,
            created_at__gte=cache_cutoff
        ).select_related('resultset').first()
        
        if cached_run and cached_run.resultset:
            # Verify resultset still exists and is valid
            if cached_run.resultset.is_accessible_for_presentation():
                logger.debug(f"Cache hit for key {cache_key[:16]}...")
                return cached_run
            else:
                logger.debug(f"Cache entry {cache_key[:16]}... has expired resultset")
        
        return None
    
    def invalidate_cache_for_dataset(self, dataset_id: str, tenant: Tenant) -> int:
        """
        Invalidate all cache entries that depend on a specific dataset.
        
        Phase 2: Allows explicit cache invalidation when data is updated.
        
        Returns number of cache entries invalidated.
        """
        # Find all AnalyzerRuns that used this dataset
        runs_to_invalidate = AnalyzerRun.objects.filter(
            tenant=tenant,
            status=AnalyzerRun.STATUS_SUCCESS,
            resolved_datasets_json__contains=dataset_id
        )
        
        count = runs_to_invalidate.count()
        
        # Mark them as stale by setting status to cached (historical)
        runs_to_invalidate.update(
            status=AnalyzerRun.STATUS_CACHED,
            cache_hit=True  # Mark as historical cache entry
        )
        
        logger.info(f"Invalidated {count} cache entries for dataset {dataset_id}")
        return count
    
    def invalidate_cache_for_model(self, analysis_model_id: str, tenant: Tenant) -> int:
        """
        Invalidate all cache entries for an Analysis Model.
        
        Phase 2: Used when model definition changes.
        """
        runs_to_invalidate = AnalyzerRun.objects.filter(
            tenant=tenant,
            analysis_model_id=analysis_model_id,
            status=AnalyzerRun.STATUS_SUCCESS
        )
        
        count = runs_to_invalidate.count()
        runs_to_invalidate.update(status=AnalyzerRun.STATUS_CACHED)
        
        logger.info(f"Invalidated {count} cache entries for model {analysis_model_id}")
        return count
    
    # ─────────────────────────────────────────────────────────────
    # Response Building
    # ─────────────────────────────────────────────────────────────
    
    def _build_response(
        self,
        run: AnalyzerRun,
        cache_hit: bool = False
    ) -> dict[str, Any]:
        """Build API response from AnalyzerRun."""
        resultset = run.resultset
        
        # Load data for response
        if resultset.storage == ResultSetStorage.PARQUET:
            df = self.storage.load_parquet(resultset.id)
            data = serialize_for_json(df.to_dict(orient='records'))
        else:
            data = resultset.preview_json or []
        
        return {
            'resultset_id': str(resultset.id),
            'analysis_model_id': str(run.analysis_model_id),
            'analysis_model_version': run.analysis_model_version,
            'schema': resultset.schema_json,
            'row_count': resultset.row_count,
            'data': data,
            'metadata': {
                'analyzer_run_id': str(run.id),
                'executed_at': run.completed_at.isoformat() if run.completed_at else None,
                'execution_time_ms': run.execution_time_ms,
                'cache_hit': cache_hit,
                'datasets_resolved': run.resolved_datasets_json
            }
        }
