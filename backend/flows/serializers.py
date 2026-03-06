from rest_framework import serializers

from .models import Flow, FlowGraphVersion, FlowVersion, FlowVersionStatus


class FlowCreateSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=Flow.STATUS_CHOICES, default="active")
    is_enabled = serializers.BooleanField(read_only=True)
    expected_version_id = serializers.UUIDField(
        required=False,
        write_only=True,
        help_text="Expected current version ID for optimistic locking. If provided, save will fail if version has changed."
    )

    class Meta:
        model = Flow
        fields = [
            "id",
            "name",
            "description",
            "status",
            "is_enabled",
            "created_at",
            "updated_at",
            "expected_version_id",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_enabled"]

    def validate_status(self, value):
        """Allow 'archived' and allow reactivation (archived → active)."""
        if value not in dict(Flow.STATUS_CHOICES):
            raise serializers.ValidationError(f"Status must be one of: {list(dict(Flow.STATUS_CHOICES).keys())}")
        if self.instance and value == "archived":
            if self.instance.status == "active" and self.instance.published_version_id is not None:
                raise serializers.ValidationError(
                    "Cannot archive an active flow with a published version. Deactivate (toggle-active) or archive the version first."
                )
        return value

    def validate(self, attrs):
        expected_version_id = attrs.pop("expected_version_id", None)
        if expected_version_id and self.instance:
            # Try new FlowVersion first, fall back to FlowGraphVersion
            current_version = self.instance.versions.order_by("-created_at").first()
            if not current_version:
                current_version = self.instance.graph_versions.order_by("-created_at").first()
            if current_version and str(current_version.id) != str(expected_version_id):
                raise serializers.ValidationError({
                    "version_conflict": True,
                    "message": "Flow has been modified. Please refresh and try again.",
                    "current_version_id": str(current_version.id) if current_version else None,
                    "expected_version_id": str(expected_version_id),
                })
        return attrs


class FlowGraphVersionSerializer(serializers.ModelSerializer):
    """Serializer for FlowGraphVersion (legacy) to include version ID in responses."""
    
    class Meta:
        model = FlowGraphVersion
        fields = [
            "id",
            "major",
            "minor",
            "is_published",
            "graph",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class FlowVersionSerializer(serializers.ModelSerializer):
    """Serializer for the new FlowVersion model with FSM lifecycle."""
    
    is_editable = serializers.BooleanField(read_only=True)
    is_draft = serializers.BooleanField(read_only=True)
    is_testing = serializers.BooleanField(read_only=True)
    is_published = serializers.BooleanField(read_only=True)
    is_archived = serializers.BooleanField(read_only=True)
    version_label = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    ctx_schema = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = FlowVersion
        fields = [
            "id",
            "flow",
            "version",
            "status",
            "status_display",
            "label",
            "notes",
            "graph",
            "ctx_schema",
            "created_at",
            "updated_at",
            "published_at",
            "testing_started_at",
            "created_by",
            "is_editable",
            "is_draft",
            "is_testing",
            "is_published",
            "is_archived",
            "version_label",
        ]
        read_only_fields = [
            "id", "flow", "version", "created_at", "updated_at", 
            "published_at", "testing_started_at", "created_by",
            "is_editable", "is_draft", "is_testing", "is_published", 
            "is_archived", "version_label", "status_display",
        ]

    def get_ctx_schema(self, obj: FlowVersion) -> dict:
        from flows.core.internal_contract import compile_ctx_schema
        graph = obj.graph if isinstance(getattr(obj, "graph", None), dict) else {}
        return compile_ctx_schema(graph or {})


class FlowVersionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new FlowVersion instances."""
    
    class Meta:
        model = FlowVersion
        fields = ["label", "notes", "graph"]
    
    def create(self, validated_data):
        flow = self.context.get('flow')
        user = self.context.get('user')
        validated_data['flow'] = flow
        validated_data['tenant'] = flow.tenant
        validated_data['created_by'] = user
        return super().create(validated_data)


class FlowVersionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating FlowVersion instances (only draft/testing)."""
    
    class Meta:
        model = FlowVersion
        fields = ["label", "notes", "graph"]
    
    def validate(self, attrs):
        if self.instance and not self.instance.is_editable:
            raise serializers.ValidationError(
                "Cannot modify published or archived versions."
            )
        return attrs

