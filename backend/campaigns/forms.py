from django import forms
from django.forms import formset_factory
from campaigns.models import Campaign, Audience, AudienceKind
from django import forms


class CampaignBasicForm(forms.ModelForm):
    """Step 1: Basic campaign information only"""
    class Meta:
        model = Campaign
        fields = ["name", "description", "channel", "kind"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter campaign name"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Campaign description (optional)"}),
            "channel": forms.Select(attrs={"class": "form-select"}, ),
            "kind": forms.Select(attrs={"class": "form-select"}),
        }

    def save(self, commit=True):
        campaign = super().save(commit=False)
        # Always set status to draft for new campaigns
        campaign.status = 'draft'
        if commit:
            campaign.save()
        return campaign


class AudienceBasicForm(forms.ModelForm):
    class Meta:
        model = Audience
        fields = ("name", "description", "kind")
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Audience Name",
                "required": "required",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Optional description...",
            }),
            "kind": forms.Select(attrs={"class": "form-select"}),
        }

    # Present nice labels but store normalized values
    # kind = forms.ChoiceField(choices=AudienceKind, widget=forms.Select(attrs={"class": "form-select"}))

    #def clean_kind(self):
    #    val = self.cleaned_data.get("kind") or ""
    #    return val.upper()

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Audience name is required.")
        return name


# ---- Step 2 (Dynamic): ConditionForm + FormSet -----------------------------
# Keep it intentionally simple & compatible with your current rules builder.
# You can expand FIELDS/choices to match your real Contact schema.

# Example allowed fields for filtering contacts:
FIELD_CHOICES = [
    ("email__icontains", "Email contains"),
    ("phone__icontains", "Phone contains"),
    ("ctype_iexact", "Type is"),
    ("company_icontains", "Company contains"),
    ("fullname__icontains", "Name contains"),
    ("city__iexact", "City equals"),
    ("country__iexact", "Country equals"),
    ("tag__in", "Has any of tags (comma-separated)"),
    ("created_at__gte", "Created at >= (YYYY-MM-DD)"),
    ("created_at__lte", "Created at <= (YYYY-MM-DD)"),
]


class ConditionForm(forms.Form):
    field = forms.ChoiceField(choices=FIELD_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    value = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    # For can_delete support in the UI:
    DELETE = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def clean(self):
        cleaned = super().clean()
        # Basic normalization for comma-separated lists when using __in
        field = cleaned.get("field") or ""
        value = cleaned.get("value")
        if field.endswith("__in") and isinstance(value, str):
            cleaned["value"] = [v.strip() for v in value.split(",") if v.strip()]
        return cleaned


ConditionFormSet = formset_factory(
    ConditionForm,
    extra=0,
    can_delete=True,
)