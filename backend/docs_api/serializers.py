"""
Serializers for Documentation API.
"""
from rest_framework import serializers
from .models import GuideCategory, Guide, CodeExample, ApiEndpointNote


class GuideListSerializer(serializers.ModelSerializer):
    """Serializer for guide listings."""
    
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    
    class Meta:
        model = Guide
        fields = ["id", "slug", "title", "summary", "category_name", "category_slug", "updated_at"]


class GuideDetailSerializer(serializers.ModelSerializer):
    """Serializer for full guide content."""
    
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    
    class Meta:
        model = Guide
        fields = [
            "id", "slug", "title", "summary", "content",
            "category_name", "category_slug",
            "created_at", "updated_at"
        ]


class GuideCategorySerializer(serializers.ModelSerializer):
    """Serializer for guide categories with nested guides."""
    
    guides = GuideListSerializer(many=True, read_only=True)
    
    class Meta:
        model = GuideCategory
        fields = ["id", "slug", "name", "description", "icon", "guides"]


class CodeExampleSerializer(serializers.ModelSerializer):
    """Serializer for code examples."""
    
    language_display = serializers.CharField(source="get_language_display", read_only=True)
    
    class Meta:
        model = CodeExample
        fields = ["id", "operation_id", "language", "language_display", "title", "code", "description"]


class ApiEndpointNoteSerializer(serializers.ModelSerializer):
    """Serializer for endpoint notes."""
    
    class Meta:
        model = ApiEndpointNote
        fields = ["id", "operation_id", "note_type", "title", "content"]


class NavigationItemSerializer(serializers.Serializer):
    """Navigation structure item."""
    
    type = serializers.CharField()  # 'category', 'guide', 'api-tag'
    slug = serializers.CharField()
    title = serializers.CharField()
    icon = serializers.CharField(required=False, allow_blank=True)
    children = serializers.ListField(child=serializers.DictField(), required=False)


class EndpointSummarySerializer(serializers.Serializer):
    """Summary of an API endpoint for listings."""
    
    operation_id = serializers.CharField()
    path = serializers.CharField()
    method = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    deprecated = serializers.BooleanField(default=False)
