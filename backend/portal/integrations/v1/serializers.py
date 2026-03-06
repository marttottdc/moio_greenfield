from rest_framework import serializers

from portal.integrations.v1.models import ExternalAccount, EmailAccount, CalendarAccount


class ExternalAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalAccount
        fields = [
            "id",
            "provider",
            "ownership",
            "email_address",
            "is_active",
            "owner_user",
        ]
        read_only_fields = ["id", "owner_user"]


class EmailAccountSerializer(serializers.ModelSerializer):
    external_account = ExternalAccountSerializer()

    class Meta:
        model = EmailAccount
        fields = ["id", "external_account", "inbox"]
        read_only_fields = fields


class CalendarAccountSerializer(serializers.ModelSerializer):
    external_account = ExternalAccountSerializer()

    class Meta:
        model = CalendarAccount
        fields = ["id", "external_account", "calendar_id"]
        read_only_fields = fields


class EmailMessageSerializer(serializers.Serializer):
    id = serializers.CharField()
    thread_id = serializers.CharField(allow_null=True, required=False)
    from_email = serializers.CharField(source="from")
    to = serializers.ListField(child=serializers.CharField())
    subject = serializers.CharField(allow_null=True, required=False)
    text = serializers.CharField(allow_null=True, required=False)
    html = serializers.CharField(allow_null=True, required=False)
    attachments = serializers.ListField(child=serializers.DictField(), required=False)
    received_at = serializers.CharField(allow_null=True, required=False)


class SendEmailSerializer(serializers.Serializer):
    to = serializers.ListField(child=serializers.EmailField(), allow_empty=False)
    cc = serializers.ListField(child=serializers.EmailField(), required=False)
    bcc = serializers.ListField(child=serializers.EmailField(), required=False)
    subject = serializers.CharField(required=False, allow_blank=True)
    text = serializers.CharField(required=False, allow_blank=True)
    html = serializers.CharField(required=False, allow_blank=True)
    attachments = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )


class CalendarEventSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField(allow_null=True, required=False)
    start = serializers.CharField(allow_null=True, required=False)
    end = serializers.CharField(allow_null=True, required=False)
    attendees = serializers.ListField(child=serializers.CharField(), required=False)


class CreateCalendarEventSerializer(serializers.Serializer):
    title = serializers.CharField(required=True)
    start = serializers.CharField(required=True)
    end = serializers.CharField(required=True)
    attendees = serializers.ListField(child=serializers.EmailField(), required=False, allow_empty=True)

