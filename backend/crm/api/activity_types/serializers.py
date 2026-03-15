"""Serializers for activity-types API OpenAPI documentation."""
from rest_framework import serializers


class ActivityTypeResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField()
    label = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    category_label = serializers.CharField()
    schema = serializers.JSONField(allow_null=True)
    default_duration_minutes = serializers.IntegerField(allow_null=True)
    default_visibility = serializers.CharField()
    default_status = serializers.CharField()
    sla_days = serializers.IntegerField(allow_null=True)
    icon = serializers.CharField(allow_blank=True)
    color = serializers.CharField(allow_blank=True)
    requires_contact = serializers.BooleanField()
    requires_deal = serializers.BooleanField()
    title_template = serializers.CharField(allow_blank=True)
    order = serializers.IntegerField()


class ActivityTypeCreateRequestSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="Required")
    label = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False)
    schema = serializers.JSONField(required=False, allow_null=True)
    default_duration_minutes = serializers.IntegerField(required=False, allow_null=True)
    default_visibility = serializers.CharField(required=False)
    default_status = serializers.CharField(required=False)
    sla_days = serializers.IntegerField(required=False, allow_null=True)
    icon = serializers.CharField(required=False, allow_blank=True)
    color = serializers.CharField(required=False, allow_blank=True)
    requires_contact = serializers.BooleanField(required=False)
    requires_deal = serializers.BooleanField(required=False)
    title_template = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False)


class ActivityTypeUpdateRequestSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False)
    schema = serializers.JSONField(required=False, allow_null=True)
    default_duration_minutes = serializers.IntegerField(required=False, allow_null=True)
    default_visibility = serializers.CharField(required=False)
    default_status = serializers.CharField(required=False)
    sla_days = serializers.IntegerField(required=False, allow_null=True)
    icon = serializers.CharField(required=False, allow_blank=True)
    color = serializers.CharField(required=False, allow_blank=True)
    requires_contact = serializers.BooleanField(required=False)
    requires_deal = serializers.BooleanField(required=False)
    title_template = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False)
