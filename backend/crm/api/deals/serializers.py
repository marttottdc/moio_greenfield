from rest_framework import serializers
from crm.models import Deal, Pipeline, PipelineStage, Contact, Customer, DealStatusChoices, DealPriorityChoices
from central_hub.models import MoioUser


def _request_tenant(request):
    if not request:
        return None
    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        return tenant
    user = getattr(request, "user", None)
    return getattr(user, "tenant", None) if user else None


class TenantScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        request = self.context.get('request')
        tenant = _request_tenant(request)
        if tenant is not None:
            queryset = super().get_queryset()
            if queryset is not None:
                return queryset.filter(tenant=tenant)
        return super().get_queryset()


class ContactPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        request = self.context.get('request')
        tenant = _request_tenant(request)
        if tenant is not None:
            return Contact._base_manager.filter(tenant=tenant)
        return Contact._base_manager.none()


class PipelineStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineStage
        fields = [
            'id', 'name', 'description', 'order', 'probability',
            'is_won_stage', 'is_lost_stage', 'color'
        ]
        read_only_fields = ['id']


class PipelineSerializer(serializers.ModelSerializer):
    stages = PipelineStageSerializer(many=True, read_only=True)
    deal_count = serializers.SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = [
            'id', 'name', 'description', 'is_default', 'is_active',
            'stages', 'deal_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_deal_count(self, obj):
        return obj.deals.count()


class PipelineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pipeline
        fields = ['name', 'description', 'is_default', 'is_active']


class DealSerializer(serializers.ModelSerializer):
    contact_name = serializers.SerializerMethodField()
    pipeline_name = serializers.SerializerMethodField()
    stage_name = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    weighted_value = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = Deal
        fields = [
            'id', 'title', 'description',
            'contact', 'contact_name', 'customer',
            'pipeline', 'pipeline_name',
            'stage', 'stage_name',
            'value', 'currency', 'weighted_value',
            'probability', 'priority', 'status',
            'expected_close_date', 'actual_close_date',
            'owner', 'owner_name', 'created_by',
            'won_reason', 'lost_reason', 'notes',
            'metadata', 'comments', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'created_by', 'weighted_value',
            'contact', 'pipeline', 'stage', 'owner', 'comments'
        ]

    def get_contact_name(self, obj):
        if obj.contact:
            return obj.contact.fullname or obj.contact.whatsapp_name or obj.contact.email or str(obj.contact.user_id)
        return None

    def get_pipeline_name(self, obj):
        return obj.pipeline.name if obj.pipeline else None

    def get_stage_name(self, obj):
        return obj.stage.name if obj.stage else None

    def get_owner_name(self, obj):
        if obj.owner:
            return f"{obj.owner.first_name} {obj.owner.last_name}".strip() or obj.owner.email
        return None


class DealCreateSerializer(serializers.ModelSerializer):
    contact = ContactPrimaryKeyRelatedField(
        queryset=Contact._base_manager.all(),
        required=False,
        allow_null=True
    )
    pipeline = TenantScopedPrimaryKeyRelatedField(
        queryset=Pipeline.objects.all(),
        required=False,
        allow_null=True
    )
    stage = TenantScopedPrimaryKeyRelatedField(
        queryset=PipelineStage.objects.all(),
        required=False,
        allow_null=True
    )
    owner = serializers.PrimaryKeyRelatedField(
        queryset=MoioUser.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Deal
        fields = [
            'title', 'description', 'contact', 'pipeline', 'stage',
            'value', 'currency', 'priority', 'expected_close_date',
            'owner', 'notes', 'metadata'
        ]

    def validate_owner(self, value):
        if value:
            request = self.context.get('request')
            tenant = _request_tenant(request)
            if tenant is not None:
                if value.tenant_id != tenant.id:
                    raise serializers.ValidationError('Owner must belong to the same tenant.')
        return value

    def validate(self, data):
        stage = data.get('stage')
        pipeline = data.get('pipeline')
        if stage and pipeline and stage.pipeline_id != pipeline.id:
            raise serializers.ValidationError({
                'stage': 'Stage must belong to the selected pipeline.'
            })
        if stage and not pipeline:
            data['pipeline'] = stage.pipeline
        return data


class DealUpdateSerializer(serializers.ModelSerializer):
    contact = ContactPrimaryKeyRelatedField(
        queryset=Contact._base_manager.all(),
        required=False,
        allow_null=True
    )
    customer = TenantScopedPrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True
    )
    pipeline = TenantScopedPrimaryKeyRelatedField(
        queryset=Pipeline.objects.all(),
        required=False,
        allow_null=True
    )
    stage = TenantScopedPrimaryKeyRelatedField(
        queryset=PipelineStage.objects.all(),
        required=False,
        allow_null=True
    )
    owner = serializers.PrimaryKeyRelatedField(
        queryset=MoioUser.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Deal
        fields = [
            'title', 'description', 'contact', 'customer', 'pipeline', 'stage',
            'value', 'currency', 'priority', 'expected_close_date',
            'owner', 'won_reason', 'lost_reason', 'notes', 'metadata'
        ]

    def validate_owner(self, value):
        if value:
            request = self.context.get('request')
            tenant = _request_tenant(request)
            if tenant is not None:
                if value.tenant_id != tenant.id:
                    raise serializers.ValidationError('Owner must belong to the same tenant.')
        return value

    def validate(self, data):
        stage = data.get('stage')
        pipeline = data.get('pipeline', getattr(self.instance, 'pipeline', None))
        if stage and pipeline and stage.pipeline_id != pipeline.id:
            raise serializers.ValidationError({
                'stage': 'Stage must belong to the selected pipeline.'
            })
        return data


class DealStageUpdateSerializer(serializers.Serializer):
    stage_id = serializers.UUIDField()
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_stage_id(self, value):
        request = self.context.get('request')
        tenant = _request_tenant(request)
        if tenant is None:
            raise serializers.ValidationError('Unable to validate tenant.')
        try:
            stage = PipelineStage.objects.get(id=value, tenant=tenant)
            return stage
        except PipelineStage.DoesNotExist:
            raise serializers.ValidationError('Stage not found.')


class DealCommentSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)
    type = serializers.ChoiceField(choices=['general', 'stage_change'], default='general', required=False)
