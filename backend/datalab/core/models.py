"""
Core models for Data Lab.

Defines FileAsset, FileSet, DataSource, ResultSet, Snapshot, and AccumulationLog.
"""
from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from portal.models import Tenant, TenantScopedModel

User = get_user_model()


class FileAsset(TenantScopedModel):
    """Represents an uploaded file asset stored in S3."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_file_assets')
    storage_key = models.CharField(
        max_length=500,
        help_text="S3 storage key for the file"
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField(help_text="File size in bytes")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='datalab_uploaded_files')
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (detected_type, sheet_names, row_count_estimate, etc.)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'datalab_file_asset'
        verbose_name = 'File Asset'
        verbose_name_plural = 'File Assets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['tenant', 'content_type']),
        ]
    
    def __str__(self) -> str:
        return f"{self.filename} ({self.size} bytes)"


class FileSet(TenantScopedModel):
    """Collection of FileAssets that can be processed together."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_file_sets')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    files = models.ManyToManyField(FileAsset, related_name='file_sets')
    schema_hint = models.JSONField(
        blank=True,
        default=dict,
        help_text="Optional: expected schema for files in this set"
    )
    
    # Tracking de acumulación
    last_snapshot = models.ForeignKey(
        'Snapshot',
        null=True,
        blank=True,
        related_name='fileset_last_snapshots',
        on_delete=models.SET_NULL,
        help_text="Último Snapshot creado para este FileSet"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'datalab_file_set'
        verbose_name = 'File Set'
        verbose_name_plural = 'File Sets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'name']),
        ]
    
    def __str__(self) -> str:
        return f"{self.name} ({self.files.count()} files)"


class DataSourceType(models.TextChoices):
    """Types of data sources in Data Lab."""
    FILE = 'file', 'File'
    FILESET = 'fileset', 'FileSet'
    CRM = 'crm', 'CRM View'
    RESULTSET = 'resultset', 'ResultSet'
    SNAPSHOT = 'snapshot', 'Snapshot'


class DataSource(TenantScopedModel):
    """Abstraction for any queryable data source in Data Lab."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_data_sources')
    type = models.CharField(
        max_length=20,
        choices=DataSourceType.choices,
        db_index=True
    )
    ref_id = models.UUIDField(
        help_text="ID of the referenced entity (FileAsset, FileSet, CRMView, ResultSet, or Snapshot)"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    schema_json = models.JSONField(
        help_text="Column definitions: [{'name': 'col', 'type': 'string', ...}]"
    )
    acl_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Access control: {'allowed_roles': [...]}"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'datalab_data_source'
        verbose_name = 'Data Source'
        verbose_name_plural = 'Data Sources'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'type']),
            models.Index(fields=['tenant', 'name']),
            models.Index(fields=['type', 'ref_id']),
        ]
    
    def __str__(self) -> str:
        return f"{self.name} ({self.get_type_display()})"


class ResultSetOrigin(models.TextChoices):
    """Origin of a ResultSet."""
    IMPORT = 'import', 'Import'
    CRM_QUERY = 'crm_query', 'CRM Query'
    SCRIPT = 'script', 'Script'
    PIPELINE = 'pipeline', 'Pipeline'
    ANALYZER = 'analyzer', 'Analyzer'


class ResultSetStorage(models.TextChoices):
    """Storage type for a ResultSet."""
    MEMORY = 'memory', 'Memory'
    PARQUET = 'parquet', 'Parquet'
    DBTEMP = 'dbtemp', 'DB Temp'


class ResultSet(TenantScopedModel):
    """Result of an execution (import, query, script, pipeline)."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_result_sets')
    name = models.CharField(max_length=200, blank=True)
    origin = models.CharField(
        max_length=20,
        choices=ResultSetOrigin.choices,
        db_index=True
    )
    schema_json = models.JSONField(
        help_text="Column definitions: [{'name': 'col', 'type': 'string', 'nullable': bool}]"
    )
    row_count = models.PositiveIntegerField(default=0)
    storage = models.CharField(
        max_length=20,
        choices=ResultSetStorage.choices,
        default=ResultSetStorage.MEMORY
    )
    storage_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="S3 key for parquet storage if storage=parquet"
    )
    preview_json = models.JSONField(
        default=list,
        blank=True,
        help_text="Sample rows (limited to 200 rows)"
    )
    lineage_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Lineage information: {'inputs': [...], 'params': {...}, 'versions': {...}}"
    )
    is_json_object = models.BooleanField(
        default=False,
        help_text="True when this ResultSet stores a JSON Object instead of tabular data."
    )
    durability = models.CharField(
        max_length=20,
        choices=[
            ('ephemeral', 'Ephemeral'),  # Temporary, auto-cleanup
            ('durable', 'Durable'),      # Persistent, becomes DatasetVersion
        ],
        default='ephemeral',
        help_text="Durability level - ephemeral for previews, durable for datasets"
    )
    dataset_version = models.OneToOneField(
        'DatasetVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='result_set_ref',
        help_text="DatasetVersion if this ResultSet was promoted to a dataset"
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='datalab_created_result_sets')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Auto-cleanup timestamp for temporary ResultSets"
    )
    
    class Meta:
        db_table = 'datalab_result_set'
        verbose_name = 'Result Set'
        verbose_name_plural = 'Result Sets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'origin']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['expires_at']),  # For cleanup queries
        ]
    
    def __str__(self) -> str:
        name_part = f" - {self.name}" if self.name else ""
        return f"{self.get_origin_display()}{name_part} ({self.row_count} rows)"
    
    def is_accessible_for_presentation(self) -> bool:
        """
        Check if this ResultSet can be used in Panels/Widgets.
        
        Fencing rule: Only durable ResultSets or Analyzer outputs
        are accessible for presentation.
        
        Returns:
            True if accessible for presentation, False otherwise
        """
        # Analyzer outputs are always accessible
        if self.origin == ResultSetOrigin.ANALYZER:
            return True
        
        # Durable ResultSets (promoted to Dataset) are accessible
        if self.durability == 'durable':
            return True
        
        # Everything else is fenced
        return False


class Snapshot(TenantScopedModel):
    """Versioned materialization of a ResultSet for stable consumption."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_snapshots')
    name = models.CharField(max_length=200)
    version = models.PositiveIntegerField(default=1)
    resultset = models.ForeignKey(
        ResultSet,
        on_delete=models.CASCADE,
        related_name='snapshots'
    )
    description = models.TextField(blank=True)
    
    # Tracking de acumulación
    fileset = models.ForeignKey(
        FileSet,
        null=True,
        blank=True,
        related_name='snapshots',
        on_delete=models.CASCADE,
        help_text="FileSet asociado (si este snapshot es resultado de acumulación)"
    )
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='datalab_created_snapshots')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'datalab_snapshot'
        verbose_name = 'Snapshot'
        verbose_name_plural = 'Snapshots'
        unique_together = ('tenant', 'name', 'version')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'name', '-version']),
            models.Index(fields=['fileset', '-created_at']),
        ]
    
    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class AccumulationLog(TenantScopedModel):
    """Log of which files were processed in each accumulation."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_accumulation_logs')
    snapshot = models.ForeignKey(
        Snapshot,
        on_delete=models.CASCADE,
        related_name='accumulation_logs'
    )
    fileset = models.ForeignKey(
        FileSet,
        on_delete=models.CASCADE,
        related_name='accumulation_logs'
    )
    processed_files = models.ManyToManyField(
        FileAsset,
        related_name='accumulation_logs',
        help_text="Files processed in this accumulation"
    )
    row_count_added = models.PositiveIntegerField(
        default=0,
        help_text="Number of rows added in this accumulation"
    )
    row_count_total = models.PositiveIntegerField(
        default=0,
        help_text="Total number of rows after this accumulation"
    )
    is_rebuild = models.BooleanField(
        default=False,
        help_text="If True, this was a full rebuild (processed all files)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'datalab_accumulation_log'
        verbose_name = 'Accumulation Log'
        verbose_name_plural = 'Accumulation Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['fileset', '-created_at']),
            models.Index(fields=['snapshot']),
        ]
    
    def __str__(self) -> str:
        action = "rebuild" if self.is_rebuild else "incremental"
        return f"{self.fileset.name} - {action} ({self.row_count_added} rows added)"


# ===== v3.1 ImportProcess & ImportRun Control Plane =====

class ImportProcess(TenantScopedModel):
    """Persistent, versioned definition of an import process bound to a file shape."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_import_processes')

    name = models.CharField(max_length=200, help_text="Human-readable name for the import process")
    file_type = models.CharField(
        max_length=20,
        choices=[('csv', 'CSV'), ('excel', 'Excel'), ('pdf', 'PDF')],
        help_text="Type of file this process handles"
    )
    import_data_as_json = models.BooleanField(
        default=False,
        help_text="If True, extract and store data as JSON Object instead of DataFrame."
    )

    shape_fingerprint = models.CharField(
        max_length=200,
        help_text="SHA256 fingerprint of the expected file shape"
    )
    shape_description = models.JSONField(
        help_text="Detailed description of the expected shape (pages, columns, patterns, etc.)"
    )

    structural_units = models.JSONField(
        default=list,
        help_text="List of structural unit definitions for extraction"
    )
    semantic_derivations = models.JSONField(
        default=list,
        help_text="List of semantic derivation definitions for transformation"
    )

    # Complete import contract - the authoritative configuration
    contract_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete import contract: {parser: {type, delimiter, header_row, ...}, mapping: [{source, target, type, format, clean}, ...]}"
    )

    version = models.PositiveIntegerField(default=1, help_text="Version number for this process")
    is_active = models.BooleanField(default=True, help_text="Whether this process version is active")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'datalab_import_process'
        verbose_name = 'Import Process'
        verbose_name_plural = 'Import Processes'
        unique_together = ('tenant', 'name', 'version')  # Versioning constraint
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'file_type']),
            models.Index(fields=['tenant', 'shape_fingerprint']),
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version} ({self.get_file_type_display()})"


class ImportRun(TenantScopedModel):
    """Immutable execution record of an ImportProcess against a RawDataset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_import_runs')

    import_process = models.ForeignKey(
        ImportProcess,
        on_delete=models.CASCADE,
        related_name='runs',
        help_text="The import process that was executed"
    )
    raw_dataset = models.ForeignKey(
        FileAsset,  # Reusing FileAsset as RawDataset for now
        on_delete=models.CASCADE,
        related_name='import_runs',
        help_text="The file that was processed"
    )

    shape_match = models.JSONField(
        default=dict,
        help_text="Shape validation result: {'status': 'pass|fail', 'score': float, 'reasons': [...]}"
    )
    status = models.CharField(
        max_length=20,
        choices=[('success', 'Success'), ('failed', 'Failed')],
        help_text="Execution status"
    )
    error_message = models.TextField(
        blank=True,
        default='',
        help_text="Error message if status is 'failed'"
    )
    resultset_ids = models.JSONField(
        default=list,
        help_text="List of ResultSet IDs created by this run"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'datalab_import_run'
        verbose_name = 'Import Run'
        verbose_name_plural = 'Import Runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['import_process', 'created_at']),
            models.Index(fields=['raw_dataset']),
        ]

    def __str__(self) -> str:
        return f"Run {self.id} - {self.import_process.name} - {self.status}"


class StructuralUnit(TenantScopedModel):
    """Internal model for structural extraction definitions (not exposed as API)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_structural_units')

    import_process = models.ForeignKey(
        ImportProcess,
        on_delete=models.CASCADE,
        related_name='structural_units_model',
        help_text="The import process this unit belongs to"
    )

    kind = models.CharField(
        max_length=20,
        choices=[('tabular', 'Tabular')],  # Could be extended for PDF regions/tables
        help_text="Type of structural unit"
    )

    selector = models.JSONField(
        help_text="Selector configuration (source, sheet, range, bbox, etc.)"
    )
    extraction_params = models.JSONField(
        default=dict,
        help_text="Additional extraction parameters"
    )

    class Meta:
        db_table = 'datalab_structural_unit'
        verbose_name = 'Structural Unit'
        verbose_name_plural = 'Structural Units'
        indexes = [
            models.Index(fields=['tenant', 'import_process']),
        ]

    def __str__(self) -> str:
        return f"StructuralUnit {self.id} ({self.kind})"


class SemanticDerivation(TenantScopedModel):
    """Internal model for semantic transformation definitions (not exposed as API)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_semantic_derivations')

    import_process = models.ForeignKey(
        ImportProcess,
        on_delete=models.CASCADE,
        related_name='semantic_derivations_model',
        help_text="The import process this derivation belongs to"
    )

    inputs = models.JSONField(
        default=list,
        help_text="List of input references: [{'structural_unit_id': uuid, 'alias': str, 'mode': 'single|collect'}]"
    )
    mapping = models.JSONField(
        default=dict,
        help_text="Column mapping and transformation rules"
    )
    schema = models.JSONField(
        default=dict,
        help_text="Output schema definition"
    )

    class Meta:
        db_table = 'datalab_semantic_derivation'
        verbose_name = 'Semantic Derivation'
        verbose_name_plural = 'Semantic Derivations'
        indexes = [
            models.Index(fields=['tenant', 'import_process']),
        ]

    def __str__(self) -> str:
        return f"SemanticDerivation {self.id}"


# ===== v3.2 Dataset & DatasetVersion =====

class Dataset(TenantScopedModel):
    """
    Logical identity for a dataset with versioning.

    Represents a durable, reusable data product that can be consumed by Flows.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_datasets')
    name = models.CharField(max_length=200, help_text="Human-readable dataset name")
    description = models.TextField(blank=True, help_text="Description of what this dataset represents")
    current_version = models.OneToOneField(
        'DatasetVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text="Current active version (pointer to latest version)"
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='datalab_created_datasets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'datalab_dataset'
        verbose_name = 'Dataset'
        verbose_name_plural = 'Datasets'
        unique_together = ('tenant', 'name')
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['tenant', 'name']),
        ]

    def __str__(self) -> str:
        return f"Dataset: {self.name}"


class DatasetVersion(TenantScopedModel):
    """
    Immutable version of a Dataset.

    References a ResultSet produced by pipeline execution.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_dataset_versions')
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='versions',
        help_text="Dataset this version belongs to"
    )
    version_number = models.PositiveIntegerField(help_text="Sequential version number")
    result_set = models.OneToOneField(
        ResultSet,
        on_delete=models.CASCADE,
        related_name='dataset_version_rel',
        help_text="ResultSet containing the actual data for this version"
    )
    description = models.TextField(blank=True, help_text="Description of this version")
    is_current = models.BooleanField(
        default=False,
        help_text="Whether this is the current active version of the dataset"
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='datalab_created_dataset_versions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'datalab_dataset_version'
        verbose_name = 'Dataset Version'
        verbose_name_plural = 'Dataset Versions'
        unique_together = ('dataset', 'version_number')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['dataset', 'version_number']),
            models.Index(fields=['dataset', 'is_current']),
        ]

    def __str__(self) -> str:
        return f"{self.dataset.name} v{self.version_number}"

    def save(self, *args, **kwargs):
        # Ensure only one current version per dataset
        if self.is_current:
            DatasetVersion.objects.filter(
                dataset=self.dataset,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)
