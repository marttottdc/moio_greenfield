import django_filters

from crm.models import Contact, ContactTypeChoices
from django import forms


class ContactFilter(django_filters.FilterSet):

    contact_phone = django_filters.CharFilter(lookup_expr='icontains')
    contact_ctype = django_filters.MultipleChoiceFilter(choices=ContactTypeChoices.choices, widget=forms.Select(attrs={'class': 'form-control'}))
    contact_fullname = django_filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Contact
        fields = ['phone', 'ctype', 'fullname']