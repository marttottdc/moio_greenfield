"""
Document format validator.

Validates documents against the schema before ingestion.
"""
import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from . import schema


@dataclass
class ValidationError:
    """A single validation error."""
    field: str
    message: str
    line: Optional[int] = None
    severity: str = "error"  # error, warning, info


@dataclass
class ValidationResult:
    """Result of document validation."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    content: str = ""
    
    def add_error(self, field: str, message: str, line: int = None):
        self.errors.append(ValidationError(field, message, line, "error"))
        self.is_valid = False
    
    def add_warning(self, field: str, message: str, line: int = None):
        self.warnings.append(ValidationError(field, message, line, "warning"))
    
    def to_dict(self) -> Dict:
        return {
            "is_valid": self.is_valid,
            "errors": [{"field": e.field, "message": e.message, "line": e.line} for e in self.errors],
            "warnings": [{"field": w.field, "message": w.message, "line": w.line} for w in self.warnings],
            "frontmatter": self.frontmatter,
        }


class DocumentValidator:
    """Validates documents against the documentation schema."""
    
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```")
    LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    
    def __init__(self, valid_categories: List[str] = None, valid_endpoints: List[str] = None):
        """
        Initialize validator.
        
        Args:
            valid_categories: List of valid category slugs (fetched from DB if None)
            valid_endpoints: List of valid operation IDs (fetched from schema if None)
        """
        self.valid_categories = valid_categories or schema.VALID_CATEGORIES
        self.valid_endpoints = valid_endpoints or []
    
    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate a document file."""
        result = ValidationResult(is_valid=True)
        
        # Check file exists
        if not file_path.exists():
            result.add_error("file", f"File not found: {file_path}")
            return result
        
        # Check file naming convention
        if not re.match(schema.FILE_PATTERN, file_path.name):
            result.add_warning("filename", f"Filename should be kebab-case: {file_path.name}")
        
        # Read content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            result.add_error("file", f"Cannot read file: {e}")
            return result
        
        return self.validate_content(content)
    
    def validate_content(self, content: str) -> ValidationResult:
        """Validate document content string."""
        result = ValidationResult(is_valid=True)
        
        # Parse frontmatter
        frontmatter, body = self._parse_frontmatter(content, result)
        if frontmatter is None:
            return result
        
        result.frontmatter = frontmatter
        result.content = body
        
        # Validate frontmatter fields
        self._validate_frontmatter(frontmatter, result)
        
        # Validate content structure
        self._validate_content(body, frontmatter, result)
        
        return result
    
    def _parse_frontmatter(self, content: str, result: ValidationResult) -> Tuple[Optional[Dict], str]:
        """Parse YAML frontmatter from content."""
        match = self.FRONTMATTER_PATTERN.match(content)
        
        if not match:
            result.add_error("frontmatter", "Document must start with YAML frontmatter (---)")
            return None, content
        
        frontmatter_str = match.group(1)
        body = content[match.end():]
        
        try:
            frontmatter = yaml.safe_load(frontmatter_str)
            if not isinstance(frontmatter, dict):
                result.add_error("frontmatter", "Frontmatter must be a YAML dictionary")
                return None, body
            return frontmatter, body
        except yaml.YAMLError as e:
            result.add_error("frontmatter", f"Invalid YAML: {e}")
            return None, body
    
    def _validate_frontmatter(self, frontmatter: Dict, result: ValidationResult):
        """Validate frontmatter fields."""
        # Check required fields
        for field_name, field_type in schema.REQUIRED_FIELDS.items():
            if field_name not in frontmatter:
                result.add_error(field_name, f"Required field '{field_name}' is missing")
            elif not isinstance(frontmatter[field_name], field_type):
                result.add_error(field_name, f"Field '{field_name}' must be {field_type.__name__}")
        
        # Validate slug format
        if "slug" in frontmatter:
            slug = frontmatter["slug"]
            if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug):
                result.add_error("slug", "Slug must be kebab-case (lowercase, hyphens only)")
        
        # Validate category
        if "category" in frontmatter:
            category = frontmatter["category"]
            if category not in self.valid_categories:
                result.add_error("category", f"Invalid category '{category}'. Valid: {', '.join(self.valid_categories)}")
        
        # Validate status
        if "status" in frontmatter:
            status = frontmatter["status"]
            if status not in schema.VALID_STATUSES:
                result.add_error("status", f"Invalid status '{status}'. Valid: {', '.join(schema.VALID_STATUSES)}")
        
        # Validate optional fields types
        for field_name, (field_type, _) in schema.OPTIONAL_FIELDS.items():
            if field_name in frontmatter:
                value = frontmatter[field_name]
                if value is not None and not isinstance(value, field_type):
                    result.add_error(field_name, f"Field '{field_name}' must be {field_type.__name__}")
        
        # Validate API endpoints if specified
        if "api_endpoints" in frontmatter and self.valid_endpoints:
            for endpoint in frontmatter.get("api_endpoints", []):
                if endpoint not in self.valid_endpoints:
                    result.add_warning("api_endpoints", f"Unknown endpoint '{endpoint}'")
    
    def _validate_content(self, content: str, frontmatter: Dict, result: ValidationResult):
        """Validate document content structure."""
        rules = schema.CONTENT_RULES
        
        # Check content length
        content_length = len(content.strip())
        if content_length < rules["min_length"]:
            result.add_error("content", f"Content too short ({content_length} chars). Minimum: {rules['min_length']}")
        if content_length > rules["max_length"]:
            result.add_error("content", f"Content too long ({content_length} chars). Maximum: {rules['max_length']}")
        
        # Check for headings
        headings = self.HEADING_PATTERN.findall(content)
        if rules["require_headings"] and not headings:
            result.add_error("content", "Document must contain at least one heading")
        
        # Check heading depth
        for hashes, title in headings:
            if len(hashes) > rules["max_heading_depth"]:
                result.add_warning("content", f"Heading '{title}' is too deep (h{len(hashes)}). Max: h{rules['max_heading_depth']}")
        
        # Check for code blocks if required
        code_blocks = self.CODE_BLOCK_PATTERN.findall(content)
        if rules["require_code_blocks"] and not code_blocks:
            result.add_warning("content", "Consider adding code examples")
        
        # Get document type and validate required sections
        doc_type = frontmatter.get("type", "guide")
        if doc_type in schema.DOCUMENT_TYPES:
            type_config = schema.DOCUMENT_TYPES[doc_type]
            heading_titles = [title.strip() for _, title in headings]
            
            for required_section in type_config["required_sections"]:
                if not any(required_section.lower() in h.lower() for h in heading_titles):
                    result.add_error("content", f"Missing required section: {required_section}")
        
        # Validate internal links
        links = self.LINK_PATTERN.findall(content)
        for link_text, link_url in links:
            if link_url.startswith("/docs/"):
                # Internal doc link - could validate exists
                pass
            elif link_url.startswith("#"):
                # Anchor link - validate heading exists
                anchor = link_url[1:].lower().replace("-", " ")
                heading_texts = [title.lower() for _, title in headings]
                if not any(anchor in h for h in heading_texts):
                    result.add_warning("content", f"Anchor link '{link_url}' may be broken")


def validate_document(file_path: str) -> ValidationResult:
    """Convenience function to validate a document file."""
    validator = DocumentValidator()
    return validator.validate_file(Path(file_path))


def validate_content(content: str) -> ValidationResult:
    """Convenience function to validate document content."""
    validator = DocumentValidator()
    return validator.validate_content(content)
