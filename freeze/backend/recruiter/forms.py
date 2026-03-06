from django import forms
from django.utils.translation import gettext_lazy as _

from chatbot.models.wa_templates import WaTemplate
from crm.models import Tag, Branch
from portal.context_utils import current_tenant
from portal.models import Tenant, MoioUser
from recruiter.models import JobPosting, User

attrs_name = {
    "id": "job_posting_name",
    "class": "form-control",
    "placeholder": "Nombre del llamado"
}

attrs_psigma_link = {
    "id": "job_posting_name",
    "class": "form-control",
    "placeholder": "Link a prueba SER"
}

attrs_branch = {
    "id": "branch_field",
    "class": "form-control",
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
            "type": "datetime-local",
            "class": "form-control inline-field data",
            "data-date-format": "dd-mm-yyyyThh:mm",
            "data-minute-step": "30",
            "autoclose": "true",
            "style": "width: 30%;"
}

attrs_tags = {
    "class": "form-control",
    "placeholder": "Selecciona los tags",

}
#  <input type="text" class="form-control date" id="daterangetime" data-toggle="date-picker" data-time-picker="true" data-locale="{'format': 'DD/MM hh:mm A'}">


class JobPostingForm(forms.ModelForm):
    name = forms.CharField(label="Nombre del llamado", widget=forms.TextInput(attrs=attrs_name))

    description = forms.CharField(label="Descripción",required=True, widget=forms.Textarea(attrs=attrs_description))

    branch = forms.ModelMultipleChoiceField(queryset=Branch.objects.filter(tenant=current_tenant.get()),
                                            widget=forms.SelectMultiple(attrs={"id": "branch_field", "class": "form-control"}),
                                            required=True, )

    include_tags = forms.ModelMultipleChoiceField(queryset=Tag.objects.filter(tenant=current_tenant.get()), widget=forms.SelectMultiple(attrs=attrs_tags), required=False)
    exclude_tags = forms.ModelMultipleChoiceField(queryset=Tag.objects.filter(tenant=current_tenant.get()), widget=forms.SelectMultiple(attrs=attrs_tags), required=False)

    psigma_link = forms.URLField(label="URL Psico Test:", widget=forms.TextInput(attrs=attrs_psigma_link))

    max_age_cv = forms.IntegerField(label="Antigüedad max. de CV(días)",required=True, max_value=600, widget=forms.NumberInput(attrs={"class": "form-control", "max_length": 5}))
    vacantes = forms.IntegerField(label="Vacantes", max_value=100, required=True, widget=forms.NumberInput(attrs={"class": "form-control", "max_length": 5}))
    salary = forms.IntegerField(label="Salario Aprox.", max_value=10000000, required=False, widget=forms.NumberInput(attrs={"class": "form-control", "max_length": 5}))

    tenant = forms.ModelChoiceField(label="tenant", widget=forms.HiddenInput(), queryset=Tenant.objects.all())
    user = forms.ModelChoiceField(label="Usuario", widget=forms.HiddenInput(), queryset=MoioUser.objects.all())
    publish = forms.BooleanField(label="Publicar", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'data-toggle': 'toggle'}))
    group_interview_date = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control datetime'}))
    closure_date = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control datetime'}))
    #group_interview_date = forms.DateTimeField(widget=forms.SplitDateTimeWidget(time_attrs={'type': 'time', 'class': 'form-control timepicker pt-1'}, date_attrs={'type': 'date', 'class': 'datepicker form-control'}))
    #closure_date = forms.DateTimeField(widget=forms.SplitDateTimeWidget(time_attrs={'type': 'time', 'class': 'form-control timepicker pt-1'}, date_attrs={'type': 'date', 'class': 'datepicker form-control'}))

    class Meta:
        model = JobPosting
        fields = ['name', 'branch', 'description', 'psigma_link', 'group_interview_date', 'closure_date', 'max_age_cv', 'vacantes', 'salary', 'publish', 'tenant', 'user', 'include_tags', 'exclude_tags']
        widgets: {
            'tenant': forms.HiddenInput(),
            'user': forms.HiddenInput(),
        }
    def __init__(self, *args, **kwargs):
        super(JobPostingForm, self).__init__(*args, **kwargs)
        # Add form-wide attributes here
        self.form_attrs = {'class': 'form-horizontal', 'id': 'custom-form-id'}


attrs_msg_templates = {

    "class": "form-control",
    "rows": "5",
    "placeholder": "Mensaje que se enviará",
    "required": "True"
}


class JobPostingMessageTemplates(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = ['psicotest_template', 'invitation_template', 'reminder_template']
        widgets = {
            'psicotest_template': forms.Textarea(attrs=attrs_msg_templates),
            'invitation_template': forms.Textarea(attrs=attrs_msg_templates),
            'reminder_template': forms.Textarea(attrs=attrs_msg_templates)
        }


class AssignWhatsappTemplate(forms.Form):
    template = forms.ModelChoiceField(label=_("Template"), queryset=WaTemplate.objects.all(), widget=forms.Select(attrs={"class": "form-control"}))
    form_id = forms.CharField(widget=forms.HiddenInput(), initial='assign-whatsapp-template')


attrs_search = {
    "id": "search_landing",
    "class": "form-control",
    "placeholder": "¿Que trabajo estás buscando?"
}


class LandingSearchForm(forms.Form):
    search_term = forms.CharField(label=_("Buscar"), max_length=400, widget=forms.TimeInput(attrs=attrs_search))


class SetupChatbot(forms.Form):
    prompt = forms.CharField(label=_("Descripcion"), widget=forms.Textarea(attrs=attrs_description))
    form_id = forms.CharField(widget=forms.HiddenInput(), initial='setup-chatbot')
