from rest_framework import serializers
from crm.models import Contact


class ContactSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(read_only=True)
    tenant = serializers.CharField(source='tenant_id', read_only=True)
    ctype = serializers.CharField(source='ctype_id', read_only=True, allow_null=True)
    created = serializers.DateTimeField(format='iso-8601', read_only=True)
    
    class Meta:
        model = Contact
        fields = ['user_id', 'fullname', 'email', 'phone', 'whatsapp_name', 'created', 'ctype', 'tenant']


def _serialize_ticket(instance):
    """Serialize ticket data for WebSocket events."""
    creator_data = None
    assigned_data = None

    if instance.creator:
        creator_data = {
            "id": str(instance.creator.id),
            "fullname": instance.creator.fullname,
            "email": instance.creator.email,
            "phone": instance.creator.phone,
        }

    if instance.assigned:
        assigned_data = {
            "id": str(instance.assigned.id),
            "fullname": instance.assigned.fullname,
            "email": instance.assigned.email,
        }

    return {
        "id": str(instance.id),
        "type": instance.type,
        "service": instance.service,
        "description": instance.description,
        "status": instance.status,
        "created": instance.created.isoformat() if instance.created else None,
        "last_updated": instance.last_updated.isoformat() if instance.last_updated else None,
        "target": instance.target.isoformat() if instance.target else None,
        "creator": creator_data,
        "assigned": assigned_data,
        "origin_type": instance.origin_type,
        "origin_ref": instance.origin_ref,
    }