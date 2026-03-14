"""
Aggregate Data Lab models for Django autodiscovery.

Django imports `<app>.models` during app loading. Since this app keeps model
definitions in subpackages, importing them here ensures every model is
registered before lazy relations like `datalab.ResultSet` are resolved.
"""

from datalab.analytics.models import AnalysisModel, AnalyzerRun
from datalab.core.models import (
    AccumulationLog,
    DataSource,
    DataSourceType,
    Dataset,
    DatasetVersion,
    FileAsset,
    FileSet,
    ImportProcess,
    ImportRun,
    ResultSet,
    ResultSetOrigin,
    ResultSetStorage,
    SemanticDerivation,
    Snapshot,
    StructuralUnit,
)
from datalab.crm_sources.models import CRMView
from datalab.panels.models import Panel, Widget, WidgetType

__all__ = [
    "AccumulationLog",
    "AnalysisModel",
    "AnalyzerRun",
    "CRMView",
    "DataSource",
    "DataSourceType",
    "Dataset",
    "DatasetVersion",
    "FileAsset",
    "FileSet",
    "ImportProcess",
    "ImportRun",
    "Panel",
    "ResultSet",
    "ResultSetOrigin",
    "ResultSetStorage",
    "SemanticDerivation",
    "Snapshot",
    "StructuralUnit",
    "Widget",
    "WidgetType",
]
