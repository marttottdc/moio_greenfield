"""
Models for documentation content management.
"""
from django.db import models
import uuid


class GuideCategory(models.Model):
    """Category for organizing guides."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Icon name (e.g., 'book', 'code')")
    order = models.IntegerField(default=0)
    
    class Meta:
        verbose_name_plural = "Guide Categories"
        ordering = ["order", "name"]
    
    def __str__(self):
        return self.name


class Guide(models.Model):
    """Documentation guide/tutorial."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(GuideCategory, on_delete=models.CASCADE, related_name="guides")
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    summary = models.TextField(blank=True, help_text="Short description for listings")
    content = models.TextField(help_text="Markdown content")
    order = models.IntegerField(default=0)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["category__order", "order", "title"]
    
    def __str__(self):
        return self.title


class CodeExample(models.Model):
    """Code example for an API endpoint."""
    
    LANGUAGES = [
        ("curl", "cURL"),
        ("python", "Python"),
        ("javascript", "JavaScript"),
        ("typescript", "TypeScript"),
        ("nodejs", "Node.js"),
        ("php", "PHP"),
        ("ruby", "Ruby"),
        ("go", "Go"),
        ("java", "Java"),
        ("csharp", "C#"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation_id = models.CharField(max_length=200, db_index=True, help_text="OpenAPI operationId")
    language = models.CharField(max_length=20, choices=LANGUAGES)
    title = models.CharField(max_length=100, blank=True)
    code = models.TextField()
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ["operation_id", "language"]
        ordering = ["operation_id", "order"]
    
    def __str__(self):
        return f"{self.operation_id} - {self.language}"


class ApiEndpointNote(models.Model):
    """Additional notes/warnings for specific API endpoints."""
    
    NOTE_TYPES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("tip", "Tip"),
        ("deprecated", "Deprecated"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation_id = models.CharField(max_length=200, db_index=True)
    note_type = models.CharField(max_length=20, choices=NOTE_TYPES, default="info")
    title = models.CharField(max_length=100, blank=True)
    content = models.TextField()
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ["operation_id", "order"]
    
    def __str__(self):
        return f"{self.operation_id} - {self.note_type}"
