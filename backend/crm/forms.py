from django import forms

from crm.models import Ticket

attrs_type = {
    "id": "ticket_add_type",
    "class": "form-control",
    "placeholder": "Tipo de Ticket"
}

attrs_service = {
    "id": "ticket_service_field",
    "class": "form-control",
    "placeholder": "Servicio",
    "default": "",
}

attrs_status = {
    "id": "projectname",
    "class": "form-control",
    "placeholder": "Status"
}

attrs_description = {
    "class": "form-control",
    "id": "project-overview",
    "rows": "5",
    "placeholder": "Describir el requerimiento",
    "required": "True"
}

attrs_date = {
            "type": "datetime-local",
            "class": "form-control date",
            "data-date-format": "dd-mm-yyyyThh:mm",
            "autoclose": "true",
}

attrs_creator = {
    "id": "ticket_add_creator",
    "class": "form-control",
    "placeholder": "Creado por"
}

attrs_tenant = {
    "id": "tenant",
    "class": "form-control",
    "hidden": ""
}


class TicketAddForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['type', 'service', 'description', 'tenant']
        widgets = {
            # 'form_id': forms.HiddenInput(),
            'type': forms.Select(attrs=attrs_type),
            'service': forms.TextInput(attrs=attrs_service),
            'description': forms.Textarea(attrs=attrs_description),
            'tenant': forms.HiddenInput(attrs=attrs_tenant),

        }


