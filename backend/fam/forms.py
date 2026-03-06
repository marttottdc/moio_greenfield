from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit

from fam.models import AssetRecord, FamAssetType, AssetPolicy, FamAssetBrand, FamAssetModel
from django import forms


attrs_status = {
    "id": "projectname",
    "class": "form-control",
    "placeholder": "Status"
}


attrs_date = {"type": "date-local", "class": "form-control data", "data-date-format": "dd-mm-yyyy", "autoclose": "true"}


class AssetRecordForm(ModelForm):
    class Meta:
        model = AssetRecord

        fields = ["serial_number", "brand", "model", "type", "policy", "purchase_date", "created_date", "comment", "owner_company", "asset_image", "active", "tenant"]

        widgets = {

            'serial_number': forms.TextInput(attrs={"id": "fam_serial_number", "class": "form-control", "placeholder": "Serial Number", "required": "True"}),
            'brand': forms.Select(attrs={"id": "fam_brand", "class": "form-control", "placeholder": "Selecciona la marca", "default": ""}),
            'model': forms.Select(attrs={"id": "fam_model", "class": "form-control", "placeholder": "Selecciona el modelo", "default": ""}),
            'policy': forms.Select(attrs={"id": "fam_model", "class": "form-control", "placeholder": "Selecciona la politica", "default": ""}),
            'type': forms.Select(attrs={"id": "fam_type", "class": "form-control", "placeholder": "Selecciona el tipo", "default": ""}),
            'purchase_date': forms.DateInput(attrs={"type": "date", "class": "form-control", "data-date-format": "dd-mm-yyyy", "autoclose": "true"}),
            'owner_company': forms.Select(attrs={"id": "company_type", "class": "form-control", "placeholder": "Selecciona el tipo", "default": ""}),
            'asset_image': forms.FileInput(attrs={"class": 'form-control'}),
            'comment': forms.Textarea(attrs={"class": "form-control", "id": "fam-notes", "rows": "2", "placeholder": "Notas sobre este activo", "required": "False"}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check', 'checked': 'checked'}),
            'tenant': forms.HiddenInput(),
            'created_date': forms.HiddenInput(),
            'create_date': forms.HiddenInput(),

        }


class ExcelUploadForm(forms.Form):

    file = forms.FileField(label="Upload a file", help_text="Select the CSV file to upload.", error_messages={
                "required": "Choose the CSV file you exported from the spreadsheet"
            }, widget=forms.ClearableFileInput(attrs={"class": "form-control"}))



class SampleInputForm(forms.Form):
    x = forms.FloatField()
    y = forms.FloatField()


class FamAssetTypeForm(forms.ModelForm):
    class Meta:
        model = FamAssetType
        fields = ["id", "name", "description", "tenant"]

        widgets = {
            'tenant': forms.HiddenInput(),

        }


class AssetPolicyForm(forms.ModelForm):
    class Meta:
        model = AssetPolicy
        fields = ["name", "description", "min_days", "max_days", "enabled", "read_method", "distance_tolerance", "tenant"]

        widgets = {
            'tenant': forms.HiddenInput(),
        }


class FamAssetBrandForm(forms.ModelForm):
    class Meta:
        model = FamAssetBrand
        fields = ["name", "description", "tenant"]

        widgets = {
            'tenant': forms.HiddenInput(),
        }


class FamAssetModelForm(forms.ModelForm):
    class Meta:
        model = FamAssetModel
        fields = ["brand", "name", "description", "tenant"]

        widgets ={
            'tenant': forms.HiddenInput(),
        }