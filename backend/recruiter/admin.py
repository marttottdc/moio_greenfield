from django.contrib import admin

from recruiter.models import JobPosting, Candidate, RecruiterDocument, CandidateList, \
    RecruiterConfiguration, CandidateDistances, CandidateDraft


class CandidateAdmin(admin.ModelAdmin):
    list_display = ('contact', 'address', 'recruiter_summary', "recruiter_status", "recruiter_posting","job_posting","psicotest_score", "created")
    search_fields = ["overall_knowledge", "tags", "work_experience", "education", "contact__fullname", "contact__phone"]
    list_filter = ["recommended_branch", "tenant", "distance_evaluation_done"]


class RecruiterDocumentAdmin(admin.ModelAdmin):
    list_display = ['name', 'file', 'read', 'uploaded_at']
    search_fields = ['name']
    list_filter = ['read', 'tenant']
    readonly_fields = ['uploaded_at', 'file', 'user', 'tenant']


class CandidateListAdmin(admin.ModelAdmin):
    list_display = ['posting_id', 'candidate_document', 'status']
    search_fields = ['candidate_document']
    list_filter = ['status', 'tenant']


class CandidateDistancesAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'branch', 'distance', 'distance_category', 'duration']
    list_filter = ['distance_category', 'branch']


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'tenant_id', 'status', 'description']
    actions = ['make_preselecting_matches', 'make_coordinating_group_interview', 'make_performing_group_interview', 'make_performing_individual_interviews', 'make_closed']

    def make_preselecting_matches(self, request, queryset):
        from recruiter.core.flows import JobPostingFlow

        for job_posting in queryset:
            flow = JobPostingFlow(job_posting)
            flow.candidate_matching()
            job_posting.save()
    make_preselecting_matches.short_description = "Move to Preselecting Matches"

    def make_coordinating_group_interview(self, request, queryset):
        from recruiter.core.flows import JobPostingFlow

        for job_posting in queryset:
            flow = JobPostingFlow(job_posting)
            flow.confirm_preselection()
            job_posting.save()
    make_coordinating_group_interview.short_description = "Move to Coordinating Group Interview"

    # def make_performing_group_interview(self, request, queryset):
    #    for job_posting in queryset:
    #        flow = JobPostingFlow(job_posting)
    #        flow.confirm_group_interview_list()
    #        job_posting.save()
    # make_performing_group_interview.short_description = "Move to Performing Group Interview"

    def make_performing_individual_interviews(self, request, queryset):
        from recruiter.core.flows import JobPostingFlow

        for job_posting in queryset:
            flow = JobPostingFlow(job_posting)
            flow.confirm_shortlist()
            job_posting.save()
    make_performing_individual_interviews.short_description = "Move to Performing Individual Interviews"

    def make_closed(self, request, queryset):
        from recruiter.core.flows import JobPostingFlow

        for job_posting in queryset:
            flow = JobPostingFlow(job_posting)
            flow.shortlist_results()
            job_posting.save()
    make_closed.short_description = "Move to Closed"


# Register your models here.

admin.site.register(Candidate, CandidateAdmin)
admin.site.register(RecruiterDocument, RecruiterDocumentAdmin)
admin.site.register(CandidateList, CandidateListAdmin)
admin.site.register(RecruiterConfiguration)
admin.site.register(CandidateDistances, CandidateDistancesAdmin)
admin.site.register(CandidateDraft)
