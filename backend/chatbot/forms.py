from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from chatbot.models.wa_templates import WaTemplate

attrs_name = {
    "id": "job_posting_name",
    "class": "form-control",
    "placeholder": "Nombre de la convocatoria"
}

attrs_branch = {
    "id": "projectname",
    "class": "form-control",
    "placeholder": "Selecciona la sucursal"
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
    "placeholder": "Ingresar la descripción de la convocatoria, esto ayuda a afinar la búsqueda",
    "required": "True"
}

attrs_date = {

    "class": "form-control datetimepicker-input",
    'type': 'datetime-local',
    "data-date-format": "dd-mm-yyyy hh:mm",
    "data-date-autoclose": "true",
    "data-provide": "datetimepicker",
    "autoclose": "True"
}


class CreateCampaignForm(forms.Form):

    name = forms.CharField(label=_("Nombre"), max_length=100, widget=forms.TextInput(attrs=attrs_name))
    description = forms.CharField(label=_("Descripcion"), widget=forms.Textarea(attrs=attrs_description))
    start_date = forms.DateTimeField(label=_("Fecha Inicio"), initial=timezone.now(),widget=forms.DateTimeInput(attrs=attrs_date))
    end_date = forms.DateTimeField(label=_("Fecha de Cierre"), widget=forms.DateTimeInput(attrs=attrs_date))
    wa_template = forms.ModelChoiceField(label=_("Template"), queryset=WaTemplate.objects.all().order_by("name"), widget=forms.Select(attrs={"class": "form-control"}))

