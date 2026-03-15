"""Serializers for tags API OpenAPI documentation."""
from rest_framework import serializers


class TagResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    context = serializers.CharField(allow_null=True)
    created_at = serializers.CharField()
    updated_at = serializers.CharField()


class TagCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(help_text="Required")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    context = serializers.CharField(required=False, allow_null=True)


class TagUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    context = serializers.CharField(required=False, allow_null=True)
