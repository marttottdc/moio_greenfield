from django import forms
from django.contrib.auth import get_user_model
from central_hub.models import Tenant, TenantConfiguration


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


# ==========================

class PsigmaIntegrationConfigForm(forms.ModelForm):
    class Meta:
        model = TenantConfiguration
        fields = ['tenant', 'psigma_integration_enabled', 'psigma_user', 'psigma_password', 'psigma_token', 'psigma_url']


class GoogleIntegrationConfigForm(forms.ModelForm):
    class Meta:
        model = TenantConfiguration
        fields = ['tenant', 'google_integration_enabled', 'google_api_key']


class OpenaiIntegrationConfigForm(forms.ModelForm):

    class Meta:
        model = TenantConfiguration
        fields = ['tenant', 'openai_integration_enabled', 'openai_api_key', 'openai_max_retries']

