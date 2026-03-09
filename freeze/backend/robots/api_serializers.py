from __future__ import annotations

from rest_framework import serializers


class RobotSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    tenant_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True, required=False)
    system_prompt = serializers.CharField(allow_blank=True, required=False)
    bootstrap_context = serializers.JSONField(required=False)
    model_config = serializers.JSONField(required=False)
    tools_config = serializers.JSONField(required=False)
    targets = serializers.JSONField(required=False)
    operation_window = serializers.JSONField(required=False)
    schedule = serializers.JSONField(required=False)
    compaction_config = serializers.JSONField(required=False)
    rate_limits = serializers.JSONField(required=False)
    enabled = serializers.BooleanField(required=False)
    hard_timeout_seconds = serializers.IntegerField(required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class RobotCreateSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True, required=False)
    system_prompt = serializers.CharField(allow_blank=True, required=False)
    bootstrap_context = serializers.JSONField(required=False)
    model_config = serializers.JSONField(required=False)
    tools_config = serializers.JSONField(required=False)
    targets = serializers.JSONField(required=False)
    operation_window = serializers.JSONField(required=False)
    schedule = serializers.JSONField(required=False)
    compaction_config = serializers.JSONField(required=False)
    rate_limits = serializers.JSONField(required=False)
    enabled = serializers.BooleanField(required=False)
    hard_timeout_seconds = serializers.IntegerField(required=False)


class RobotTriggerSerializer(serializers.Serializer):
    instruction_schema_version = serializers.IntegerField(required=False, default=1)
    instruction = serializers.CharField(required=False, allow_blank=True)
    objective_override = serializers.JSONField(required=False)
    queue_items = serializers.ListField(required=False, child=serializers.JSONField())
    constraints = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)
    session_key = serializers.CharField(required=False, allow_blank=True)
    trigger_source = serializers.CharField(required=False, allow_blank=True)


class RobotSessionSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    robot_id = serializers.UUIDField(read_only=True)
    session_key = serializers.CharField()
    run_id = serializers.UUIDField(allow_null=True, required=False)
    metadata = serializers.JSONField(required=False)
    intent_state = serializers.JSONField(required=False)
    transcript = serializers.JSONField(required=False)
    transcript_entries = serializers.IntegerField(required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class RobotRunSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    robot_id = serializers.UUIDField(read_only=True)
    session_id = serializers.UUIDField(allow_null=True, required=False)
    session_key = serializers.CharField(required=False, allow_null=True)
    status = serializers.CharField()
    trigger_source = serializers.CharField()
    trigger_payload = serializers.JSONField(required=False)
    usage = serializers.JSONField(required=False)
    execution_context = serializers.JSONField(required=False)
    intent_state = serializers.JSONField(required=False)
    output_data = serializers.JSONField(required=False)
    error_data = serializers.JSONField(required=False)
    cancel_requested_at = serializers.DateTimeField(allow_null=True, required=False)
    started_at = serializers.DateTimeField(allow_null=True, required=False)
    completed_at = serializers.DateTimeField(allow_null=True, required=False)


class RobotEventSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    robot_id = serializers.UUIDField(read_only=True)
    run_id = serializers.UUIDField(allow_null=True, required=False)
    session_id = serializers.UUIDField(allow_null=True, required=False)
    event_type = serializers.CharField()
    payload = serializers.JSONField()
    created_at = serializers.DateTimeField(read_only=True)


class RobotMemorySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    robot_id = serializers.UUIDField(read_only=True)
    session_id = serializers.UUIDField(allow_null=True, required=False)
    kind = serializers.CharField()
    payload = serializers.JSONField()
    created_at = serializers.DateTimeField(read_only=True)
    expires_at = serializers.DateTimeField(allow_null=True, required=False)


class RobotMemoryCreateSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(required=False)
    kind = serializers.CharField(required=False, default="fact")
    payload = serializers.JSONField(required=False, default=dict)
    expires_at = serializers.DateTimeField(required=False)


class UpdateIntentStateSerializer(serializers.Serializer):
    intent_state = serializers.JSONField()
