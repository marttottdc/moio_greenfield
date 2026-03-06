from recruiter.core.flows import JobPostingFlow
from recruiter.models import JobPosting
from recruiter.models import Tenant
from recruiter.models import JobPostingStatus

tenant = Tenant.objects.get(pk=3)
jp = JobPosting(name="Prueba x", description="Necesitamos humanos", tenant=tenant)
jp.save()


# jp_flow = JobPostingFlow(jp)
#
#
# while jp_flow._get_status() != JobPostingStatus.CLOSED:
#
#     print("status actual", jp_flow._get_status())
#     input("press key to continue")
#
#     if jp_flow._get_status() == JobPostingStatus.NEW:
#
#         jp_flow.launch_search()
#
#     elif jp_flow._get_status() == JobPostingStatus.PRESELECTING_MATCHES:
#
#         jp_flow.confirm_preselection()
#
#     elif jp_flow._get_status() == JobPostingStatus.COORDINATING_GROUP_INTERVIEW:
#
#         jp_flow.confirm_group_interview_list()
#
#     elif jp_flow._get_status() == JobPostingStatus.PERFORMING_GROUP_INTERVIEW:
#
#         jp_flow.confirm_shortlist()
#
#     elif jp_flow._get_status() == JobPostingStatus.PERFORMING_INDIVIDUAL_INTERVIEWS:
#         jp_flow.shortlist_results()



