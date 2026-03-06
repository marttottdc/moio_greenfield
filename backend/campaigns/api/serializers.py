"""Serializers powering the Campaigns + Audiences API."""

from __future__ import annotations

from typing import Any, Dict, List

from rest_framework import serializers

from campaigns.models import Audience, Campaign


class AudienceSerializer(serializers.ModelSerializer):
    """Lightweight audience representation for listings."""

    class Meta:
        model = Audience
        fields = (
            "id",
            "name",
            "description",
            "kind",
            "size",
            "is_draft",
            "materialized_at",
            "created",
            "updated",
        )
        read_only_fields = fields


class AudienceDetailSerializer(AudienceSerializer):
    """Full representation including rule definition."""

    rules = serializers.JSONField(allow_null=True)

    class Meta(AudienceSerializer.Meta):
        fields = AudienceSerializer.Meta.fields + ("rules",)


class MappingItemSerializer(serializers.Serializer):
    template_var = serializers.CharField()
    target_field = serializers.CharField(allow_blank=True)
    type = serializers.ChoiceField(choices=("variable", "fixed_value"))
    template_element = serializers.CharField(required=False, allow_blank=True)


class MessageConfigSerializer(serializers.Serializer):
    whatsapp_template_id = serializers.CharField(required=False)
    map = serializers.ListField(child=MappingItemSerializer(), required=False)


class DefaultsConfigSerializer(serializers.Serializer):
    auto_correct = serializers.BooleanField(default=False)
    use_first_name = serializers.BooleanField(default=False)
    save_contacts = serializers.BooleanField(default=False)
    notify_agent = serializers.BooleanField(default=False)
    contact_type = serializers.CharField(required=False, allow_blank=True)
    country_code = serializers.CharField(required=False, allow_blank=True)


class ScheduleConfigSerializer(serializers.Serializer):
    date = serializers.DateTimeField(required=False, allow_null=True)


class CampaignConfigSerializer(serializers.Serializer):
    message = MessageConfigSerializer(required=False)
    defaults = DefaultsConfigSerializer(required=False)
    data = serializers.JSONField(required=False)
    schedule = ScheduleConfigSerializer(required=False)


class CampaignSerializer(serializers.ModelSerializer):
    """Campaign list serializer with derived insights."""

    audience_name = serializers.CharField(source="audience.name", read_only=True)
    audience_size = serializers.IntegerField(source="audience.size", read_only=True)
    open_rate = serializers.SerializerMethodField()
    ready_to_launch = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = (
            "id",
            "name",
            "description",
            "channel",
            "kind",
            "status",
            "sent",
            "opened",
            "responded",
            "audience",
            "audience_name",
            "audience_size",
            "open_rate",
            "ready_to_launch",
            "created",
            "updated",
        )
        read_only_fields = (
            "sent",
            "opened",
            "responded",
            "audience_name",
            "audience_size",
            "open_rate",
            "ready_to_launch",
            "created",
            "updated",
        )

    def get_open_rate(self, obj: Campaign) -> float:
        total = obj.sent or 0
        if total == 0:
            return 0.0
        return round((obj.opened or 0) / total * 100, 2)

    def get_ready_to_launch(self, obj: Campaign) -> bool:
        return obj.can_launch()


class CampaignDetailSerializer(CampaignSerializer):
    """Full campaign payload for the configurator."""

    config = CampaignConfigSerializer(read_only=True)
    audience = AudienceSerializer(read_only=True)
    configuration_state = serializers.SerializerMethodField()

    class Meta(CampaignSerializer.Meta):
        fields = CampaignSerializer.Meta.fields + (
            "config",
            "configuration_state",
        )
        read_only_fields = CampaignSerializer.Meta.read_only_fields + (
            "config",
            "configuration_state",
        )

    def get_configuration_state(self, obj: Campaign) -> Dict[str, bool]:
        message_cfg = obj.config.get("message", {}) if obj.config else {}
        data_cfg = obj.config.get("data", {}) if obj.config else {}
        schedule_cfg = obj.config.get("schedule", {}) if obj.config else {}
        return {
            "has_whatsapp_template": bool(message_cfg.get("whatsapp_template_id")),
            "has_mapping": bool(message_cfg.get("map")),
            "has_data": bool(data_cfg.get("data_staging")),
            "has_schedule": bool(schedule_cfg.get("date")),
        }


class CampaignAudienceSerializer(serializers.Serializer):
    audience_id = serializers.UUIDField()


class CampaignWhatsappTemplateSerializer(serializers.Serializer):
    template_id = serializers.CharField()


class CampaignDefaultsSerializer(serializers.Serializer):
    auto_correct = serializers.BooleanField(required=False)
    use_first_name = serializers.BooleanField(required=False)
    save_contacts = serializers.BooleanField(required=False)
    notify_agent = serializers.BooleanField(required=False)
    contact_type = serializers.CharField(required=False, allow_blank=True)
    country_code = serializers.CharField(required=False, allow_blank=True)


class CampaignMappingSerializer(serializers.Serializer):
    mapping = serializers.ListField(child=MappingItemSerializer())
    contact_name_field = serializers.CharField(required=False, allow_blank=True)


class AudienceRulesSerializer(serializers.Serializer):
    and_rules = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    or_rules = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )


class AudienceStaticContactsSerializer(serializers.Serializer):
    contact_ids = serializers.ListField(child=serializers.UUIDField())
    action = serializers.ChoiceField(choices=("add", "remove"))


