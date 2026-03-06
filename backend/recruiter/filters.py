import django_filters

from recruiter.models import Candidate, CandidateStatus
from django import forms


class CandidateFilter(django_filters.FilterSet):

    document_id = django_filters.CharFilter(lookup_expr='istartswith')
    recruiter_status = django_filters.MultipleChoiceFilter(choices=CandidateStatus.choices.name, attrs={'class': 'form-control'})
    contact__fullname = django_filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Candidate
        fields = ['document_id', 'recruiter_status', 'contact__fullname']