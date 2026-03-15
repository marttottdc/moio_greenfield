"""
Serializers for activities API documentation (OpenAPI request/response schemas).
Used only by extend_schema; actual request handling uses raw request.data.
"""
from rest_framework import serializers


class ActivityCreateRequestSerializer(serializers.Serializer):
    """Request body for creating an activity."""
    title = serializers.CharField(required=False, allow_blank=True, help_text="Activity title")
    kind = serializers.ChoiceField(
        choices=["note", "call", "meeting", "email", "task", "reminder"],
        default="note",
        help_text="Activity kind",
    )
    type = serializers.CharField(required=False, allow_blank=True, help_text="Activity type name or key")
    type_key = serializers.CharField(required=False, allow_blank=True, help_text="Activity type key")
    content = serializers.JSONField(required=False, help_text="Structured content (e.g. note text, call summary)")
    source = serializers.ChoiceField(
        choices=["manual", "system", "suggestion"],
        default="manual",
        help_text="Source of the activity",
    )
    visibility = serializers.CharField(required=False, default="public", help_text="Visibility")
    status = serializers.CharField(required=False, default="completed", help_text="Status")
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    duration_minutes = serializers.IntegerField(required=False, allow_null=True)
    contact_id = serializers.UUIDField(required=False, allow_null=True)
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    deal_id = serializers.UUIDField(required=False, allow_null=True)
    ticket_id = serializers.UUIDField(required=False, allow_null=True)
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    created_by_id = serializers.IntegerField(required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    needs_confirmation = serializers.BooleanField(required=False, default=False)


class ActivityUpdateRequestSerializer(serializers.Serializer):
    """Request body for PATCH (partial update) on an activity."""
    title = serializers.CharField(required=False, allow_blank=True)
    kind = serializers.ChoiceField(choices=["note", "call", "meeting", "email", "task", "reminder"], required=False)
    type = serializers.CharField(required=False, allow_blank=True)
    type_key = serializers.CharField(required=False, allow_blank=True)
    content = serializers.JSONField(required=False)
    source = serializers.ChoiceField(choices=["manual", "system", "suggestion"], required=False)
    visibility = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    duration_minutes = serializers.IntegerField(required=False, allow_null=True)
    contact_id = serializers.UUIDField(required=False, allow_null=True)
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    deal_id = serializers.UUIDField(required=False, allow_null=True)
    ticket_id = serializers.UUIDField(required=False, allow_null=True)
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    created_by_id = serializers.IntegerField(required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    reason = serializers.CharField(required=False, allow_blank=True)
    needs_confirmation = serializers.BooleanField(required=False)


class ActivityResponseSerializer(serializers.Serializer):
    """Single activity response schema for API documentation."""
    id = serializers.UUIDField()
    title = serializers.CharField()
    kind = serializers.CharField()
    kind_label = serializers.CharField()
    type = serializers.CharField(allow_null=True)
    type_key = serializers.CharField(allow_null=True)
    content = serializers.JSONField()
    source = serializers.CharField()
    visibility = serializers.CharField()
    visibility_label = serializers.CharField()
    user_id = serializers.IntegerField(allow_null=True)
    author = serializers.CharField()
    created_at = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    scheduled_at = serializers.CharField(allow_null=True)
    occurred_at = serializers.CharField(allow_null=True)
    completed_at = serializers.CharField(allow_null=True)
    duration_minutes = serializers.IntegerField(allow_null=True)
    owner_id = serializers.IntegerField(allow_null=True)
    created_by_id = serializers.IntegerField(allow_null=True)
    contact_id = serializers.UUIDField(allow_null=True)
    contact_name = serializers.CharField(allow_null=True)
    customer_id = serializers.UUIDField(allow_null=True)
    customer_name = serializers.CharField(allow_null=True)
    deal_id = serializers.UUIDField(allow_null=True)
    deal_title = serializers.CharField(allow_null=True)
    ticket_id = serializers.UUIDField(allow_null=True)
    tags = serializers.ListField(child=serializers.CharField())
    reason = serializers.CharField()
    needs_confirmation = serializers.BooleanField()


class ActivityListResponseSerializer(serializers.Serializer):
    """Paginated list of activities."""
    activities = ActivityResponseSerializer(many=True)
    pagination = serializers.DictField()


class ActivitySuggestionAcceptRequestSerializer(serializers.Serializer):
    """Optional body for accepting a suggestion (overrides)."""
    overrides = serializers.DictField(required=False, help_text="Optional field overrides when accepting")


class ActivitySuggestionResponseSerializer(serializers.Serializer):
    """Single suggestion response schema."""
    id = serializers.UUIDField()
    type_key = serializers.CharField()
    reason = serializers.CharField()
    confidence = serializers.FloatField()
    suggested_at = serializers.CharField()
    expires_at = serializers.CharField(allow_null=True)
    proposed_fields = serializers.DictField()
    target_contact_id = serializers.UUIDField(allow_null=True)
    target_customer_id = serializers.UUIDField(allow_null=True)
    target_deal_id = serializers.UUIDField(allow_null=True)
    assigned_to_id = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
    activity_record_id = serializers.UUIDField(allow_null=True)
    created_by_source = serializers.CharField(allow_null=True)


class ActivitySuggestionListResponseSerializer(serializers.Serializer):
    """Paginated list of suggestions."""
    suggestions = ActivitySuggestionResponseSerializer(many=True)
    pagination = serializers.DictField()
