"""Serializers for shared resource endpoints."""

from rest_framework import serializers


class WhatsappTemplateTestSerializer(serializers.Serializer):
    phone = serializers.CharField()
    variables = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
    )


class WhatsappTemplateComponentSerializer(serializers.Serializer):
    """Minimal representation of a template component from Meta's API."""

    type = serializers.CharField(required=False)
    format = serializers.CharField(required=False)
    text = serializers.CharField(required=False)
    buttons = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=True
    )


class WhatsappTemplateSummarySerializer(serializers.Serializer):
    """Summary data exposed when listing WhatsApp templates."""

    id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField(allow_blank=True, required=False)
    language = serializers.CharField()
    status = serializers.CharField()
    components = serializers.ListField(
        child=WhatsappTemplateComponentSerializer(), required=False, allow_empty=True
    )


class WhatsappTemplateListResponseSerializer(serializers.Serializer):
    """Response payload for the WhatsApp template list endpoint."""

    templates = WhatsappTemplateSummarySerializer(many=True)


class WhatsappTemplateDetailResponseSerializer(serializers.Serializer):
    """Response payload for the WhatsApp template detail endpoint."""

    template = serializers.DictField()
    requirements = serializers.ListField(child=serializers.DictField())


class WhatsappTemplateTestResponseSerializer(serializers.Serializer):
    """Response payload for WhatsApp test send action."""

    sent = serializers.BooleanField()
