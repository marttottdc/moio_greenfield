"""
Management command to ingest documents from a folder with validation.

Usage:
    python manage.py ingest_docs /path/to/docs          # Validate and import
    python manage.py ingest_docs /path/to/docs --publish # Auto-publish valid docs
    python manage.py ingest_docs /path/to/docs --validate-only # Validate without importing
    python manage.py ingest_docs --template guide       # Print template
"""
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from docs_api.ingestion import DocumentIngestor, DocumentValidator
from docs_api.ingestion.ingestor import create_template


class Command(BaseCommand):
    help = "Ingest and validate documentation from a folder"

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            nargs="?",
            type=str,
            help="Source folder containing markdown files",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Automatically publish valid documents",
        )
        parser.add_argument(
            "--validate-only",
            action="store_true",
            help="Only validate, don't import",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            default=True,
            help="Fail on warnings (default: True)",
        )
        parser.add_argument(
            "--template",
            type=str,
            choices=["guide", "tutorial", "reference", "concept"],
            help="Print a document template",
        )
        parser.add_argument(
            "--file",
            type=str,
            help="Validate/import a single file",
        )

    def handle(self, *args, **options):
        # Handle template request
        if options.get("template"):
            template = create_template(options["template"])
            self.stdout.write(template)
            return
        
        # Determine source
        source = options.get("source")
        single_file = options.get("file")
        
        if single_file:
            self._handle_single_file(single_file, options)
            return
        
        if not source:
            # Default to docs/content folder
            source = Path(settings.BASE_DIR) / "docs" / "content"
            if not source.exists():
                self.stdout.write(self.style.ERROR(
                    f"No source specified and default not found: {source}"
                ))
                self.stdout.write("Usage: python manage.py ingest_docs /path/to/docs")
                return
        
        source_path = Path(source)
        
        if not source_path.exists():
            self.stdout.write(self.style.ERROR(f"Source folder not found: {source}"))
            return
        
        # Create ingestor
        ingestor = DocumentIngestor(
            source_dir=str(source_path),
            auto_publish=options.get("publish", False),
            strict_mode=options.get("strict", True),
        )
        
        if options.get("validate_only"):
            self._validate_folder(ingestor)
        else:
            self._ingest_folder(ingestor)
    
    def _handle_single_file(self, file_path: str, options: dict):
        """Handle single file validation/import."""
        path = Path(file_path)
        
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return
        
        validator = DocumentValidator()
        result = validator.validate_file(path)
        
        self._print_validation_result(path.name, result)
        
        if result.is_valid and not options.get("validate_only"):
            ingestor = DocumentIngestor(
                source_dir=str(path.parent),
                auto_publish=options.get("publish", False),
            )
            import_result = ingestor.ingest_file(path)
            self.stdout.write(f"\nImport result: {import_result}")
    
    def _validate_folder(self, ingestor: DocumentIngestor):
        """Validate all files without importing."""
        self.stdout.write("Validating documents...\n")
        
        results = ingestor.validate_folder()
        
        valid_count = 0
        invalid_count = 0
        warning_count = 0
        
        for file_path, result in sorted(results.items()):
            filename = Path(file_path).name
            
            if result.is_valid:
                valid_count += 1
                if result.warnings:
                    warning_count += 1
                    self.stdout.write(self.style.WARNING(f"⚠ {filename}"))
                    for warn in result.warnings:
                        self.stdout.write(f"    {warn.field}: {warn.message}")
                else:
                    self.stdout.write(self.style.SUCCESS(f"✓ {filename}"))
            else:
                invalid_count += 1
                self.stdout.write(self.style.ERROR(f"✗ {filename}"))
                for error in result.errors:
                    self.stdout.write(f"    {error.field}: {error.message}")
        
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Valid: {valid_count}")
        self.stdout.write(f"Invalid: {invalid_count}")
        self.stdout.write(f"With warnings: {warning_count}")
    
    def _ingest_folder(self, ingestor: DocumentIngestor):
        """Ingest all files from folder."""
        self.stdout.write("Ingesting documents...\n")
        
        result = ingestor.ingest_all()
        
        # Print errors
        for error in result.errors:
            self.stdout.write(self.style.ERROR(
                f"✗ {error['file']}: {error['message']}"
            ))
        
        # Print summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Processed: {result.processed}")
        self.stdout.write(self.style.SUCCESS(f"Imported: {result.imported}"))
        self.stdout.write(self.style.SUCCESS(f"Updated: {result.updated}"))
        self.stdout.write(f"Skipped (unchanged): {result.skipped}")
        self.stdout.write(self.style.ERROR(f"Failed: {result.failed}"))
    
    def _print_validation_result(self, filename: str, result):
        """Print validation result for a single file."""
        if result.is_valid:
            self.stdout.write(self.style.SUCCESS(f"✓ {filename} is valid"))
        else:
            self.stdout.write(self.style.ERROR(f"✗ {filename} is invalid"))
        
        for error in result.errors:
            self.stdout.write(self.style.ERROR(f"  ERROR: {error.field}: {error.message}"))
        
        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(f"  WARNING: {warning.field}: {warning.message}"))
        
        if result.frontmatter:
            self.stdout.write("\nFrontmatter:")
            for key, value in result.frontmatter.items():
                self.stdout.write(f"  {key}: {value}")
