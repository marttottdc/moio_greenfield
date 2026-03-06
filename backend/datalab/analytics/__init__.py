"""
Analytics module for Moio Data Lab.

This module provides:
- AnalysisModel: Declarative definition of analytical intent
- AnalyzerRun: Execution tracking and audit
- AnalyzerService: The only component that executes analytics
"""

from datalab.analytics.models import AnalysisModel, AnalyzerRun

__all__ = ['AnalysisModel', 'AnalyzerRun']
