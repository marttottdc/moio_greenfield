from django import forms
from django.contrib.auth import get_user_model
from central_hub.models import Tenant


class TenantForm(forms.ModelForm):

    class Meta:
        model = Tenant
        fields = ['nombre', 'domain', 'enabled']

        widgets = {
            'nombre': forms.TextInput(attrs={"id": "tenant_name", "class": "form-control", "placeholder": "Nombre del Tenant"}),
            'domain': forms.TextInput(attrs={"id": "tenant_domain", "class": "form-control", "placeholder": "Dominio de la empresa"}),
            'enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'data-toggle': 'toggle'}),
        }


User = get_user_model()


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']


# Integration config forms removed – use IntegrationConfig via /api/v1/integrations/

