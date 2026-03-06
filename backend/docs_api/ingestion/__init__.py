"""
Document ingestion system with format validation.

Documents must follow a specific format to be published:
- YAML frontmatter with required fields
- Markdown content with required sections
- Valid references to other docs/endpoints
"""
from .validator import DocumentValidator, ValidationResult
from .ingestor import DocumentIngestor

__all__ = ["DocumentValidator", "ValidationResult", "DocumentIngestor"]
