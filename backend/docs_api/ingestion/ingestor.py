"""
Document ingestor - watches folder and imports valid documents.
"""
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from django.utils import timezone

from docs_api.models import Guide, GuideCategory
from .validator import DocumentValidator, ValidationResult
from . import schema

logger = logging.getLogger(__name__)


class IngestResult:
    """Result of an ingestion run."""
    
    def __init__(self):
        self.processed = 0
        self.imported = 0
        self.updated = 0
        self.skipped = 0
        self.failed = 0
        self.errors: List[Dict] = []
        self.warnings: List[Dict] = []
    
    def to_dict(self) -> Dict:
        return {
            "processed": self.processed,
            "imported": self.imported,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class DocumentIngestor:
    """
    Ingests documents from a folder into the database.
    
    Features:
    - Validates documents before import
    - Tracks file hashes to detect changes
    - Only updates if content changed
    - Respects status field for publishing
    """
    
    def __init__(
        self,
        source_dir: str,
        auto_publish: bool = False,
        strict_mode: bool = True,
    ):
        """
        Initialize ingestor.
        
        Args:
            source_dir: Path to folder containing markdown files
            auto_publish: Automatically publish valid documents
            strict_mode: Fail on any validation error (vs just warnings)
        """
        self.source_dir = Path(source_dir)
        self.auto_publish = auto_publish
        self.strict_mode = strict_mode
        self.validator = DocumentValidator(
            valid_categories=self._get_valid_categories()
        )
        self._hash_cache: Dict[str, str] = {}
    
    def _get_valid_categories(self) -> List[str]:
        """Get valid category slugs from database."""
        try:
            return list(GuideCategory.objects.values_list("slug", flat=True))
        except Exception:
            return schema.VALID_CATEGORIES
    
    def _compute_hash(self, content: str) -> str:
        """Compute content hash for change detection."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def ingest_all(self) -> IngestResult:
        """Ingest all markdown files from source directory."""
        result = IngestResult()
        
        if not self.source_dir.exists():
            result.errors.append({
                "file": str(self.source_dir),
                "message": "Source directory does not exist"
            })
            return result
        
        # Find all markdown files
        md_files = list(self.source_dir.rglob("*.md"))
        logger.info(f"Found {len(md_files)} markdown files in {self.source_dir}")
        
        for file_path in md_files:
            result.processed += 1
            file_result = self.ingest_file(file_path)
            
            if file_result == "imported":
                result.imported += 1
            elif file_result == "updated":
                result.updated += 1
            elif file_result == "skipped":
                result.skipped += 1
            else:
                result.failed += 1
                result.errors.append({
                    "file": str(file_path),
                    "message": file_result
                })
        
        return result
    
    def ingest_file(self, file_path: Path) -> str:
        """
        Ingest a single file.
        
        Returns:
            "imported" | "updated" | "skipped" | error message
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Cannot read file: {e}"
        
        # Validate
        validation = self.validator.validate_content(content)
        
        if not validation.is_valid:
            error_msgs = [f"{e.field}: {e.message}" for e in validation.errors]
            return f"Validation failed: {'; '.join(error_msgs)}"
        
        if self.strict_mode and validation.warnings:
            warn_msgs = [f"{w.field}: {w.message}" for w in validation.warnings]
            logger.warning(f"Warnings for {file_path}: {'; '.join(warn_msgs)}")
        
        # Check if already exists and unchanged
        frontmatter = validation.frontmatter
        slug = frontmatter["slug"]
        content_hash = self._compute_hash(content)
        
        existing = Guide.objects.filter(slug=slug).first()
        
        if existing:
            # Check if content changed
            existing_hash = (existing.content or "")[:16]  # Simple check
            stored_hash = getattr(existing, "_content_hash", None)
            
            # Compute hash of existing content for comparison
            existing_content_hash = self._compute_hash(existing.content or "")
            
            if existing_content_hash == content_hash:
                return "skipped"
        
        # Get or create category
        category_slug = frontmatter["category"]
        category = GuideCategory.objects.filter(slug=category_slug).first()
        
        if not category:
            # Auto-create category
            category = GuideCategory.objects.create(
                slug=category_slug,
                name=category_slug.replace("-", " ").title(),
                order=100,
            )
        
        # Determine publish status
        status = frontmatter.get("status", "draft")
        is_published = status == "published" or self.auto_publish
        
        # Create or update guide
        guide_data = {
            "category": category,
            "title": frontmatter["title"],
            "summary": frontmatter.get("summary", ""),
            "content": validation.content,
            "order": frontmatter.get("order", 0),
            "is_published": is_published,
        }
        
        if existing:
            for key, value in guide_data.items():
                setattr(existing, key, value)
            existing.save()
            logger.info(f"Updated guide: {slug}")
            return "updated"
        else:
            Guide.objects.create(slug=slug, **guide_data)
            logger.info(f"Imported guide: {slug}")
            return "imported"
    
    def validate_folder(self) -> Dict[str, ValidationResult]:
        """
        Validate all files in folder without importing.
        
        Returns:
            Dict mapping file paths to validation results
        """
        results = {}
        
        if not self.source_dir.exists():
            return results
        
        for file_path in self.source_dir.rglob("*.md"):
            results[str(file_path)] = self.validator.validate_file(file_path)
        
        return results
    
    def get_status(self) -> Dict:
        """Get current ingestion status."""
        db_guides = Guide.objects.count()
        db_published = Guide.objects.filter(is_published=True).count()
        
        folder_files = 0
        if self.source_dir.exists():
            folder_files = len(list(self.source_dir.rglob("*.md")))
        
        return {
            "source_dir": str(self.source_dir),
            "folder_files": folder_files,
            "db_guides": db_guides,
            "db_published": db_published,
        }


def create_template(doc_type: str = "guide") -> str:
    """
    Create a template document with proper frontmatter.
    
    Args:
        doc_type: Type of document (guide, tutorial, reference, concept)
    
    Returns:
        Template markdown string
    """
    type_config = schema.DOCUMENT_TYPES.get(doc_type, schema.DOCUMENT_TYPES["guide"])
    
    template = '''---
title: "Your Title Here"
slug: "your-slug-here"
category: "getting-started"
order: 10
status: draft
summary: "Brief description for listings"
tags: []
api_endpoints: []
---

'''
    
    # Add required sections
    for section in type_config["required_sections"]:
        template += f"## {section}\n\nContent here...\n\n"
    
    # Add optional sections as comments
    for section in type_config["optional_sections"]:
        template += f"<!-- ## {section} -->\n\n"
    
    return template
