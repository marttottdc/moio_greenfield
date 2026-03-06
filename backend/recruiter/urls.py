from django.urls import path, include

from recruiter.views import recruiter_dashboard, carga_cvs, landing_page, job_posting_add, \
    job_posting_details, \
    candidate_update, configuration, \
    receive_psigma_webhook, data_importer, job_posting_delete, \
    job_posting_update, update_recruiter_dashboard_kpis, candidate_debug, \
    recruiter_dashboard_posting_list, candidate_status_update, job_posting_action, candidate_status, \
    group_interview_debrief, register_candidate_evaluation, message_templates_configuration, candidates_list, \
    register_one_to_one, candidate_page, upload_cvs_stats, job_posting_statistics, candidate_discard, candidate_search, \
    import_generic_cv, recruiter, candidate_add, load_employees, confirm_cv_load, candidate_clusters

app_name = 'recruiter'

urlpatterns = [
    path('upload/', carga_cvs, name='carga_cvs'),
    path('upload/confirm', confirm_cv_load, name='confirm_cv_load'),

    path('upload/stats', upload_cvs_stats, name='upload_cvs_stats'),
    path('load_cv/', import_generic_cv, name='load_cv'),
    path('load_employees/', load_employees, name='load_employees'),

    path('dashboard/', recruiter_dashboard, name='dashboard'),
    path('landing', landing_page, name='landing_page'),

    path('convocatorias/candidate_update/', candidate_update, name='candidate_update'),

    path('configuration/', configuration, name='configuration'),
    path('webhooks/psigma/', receive_psigma_webhook, name='receive_psigma_webhook'),

    path('candidates/', candidates_list, name='candidates'),
    path('candidate/<int:pk>', candidate_page, name='candidate_page'),

    path('admin/import_data/', data_importer, name='data_importer'),

    path('convocatoria/dashboard/update_kpis', update_recruiter_dashboard_kpis, name="update_kpis"),
    path('recruiter/candidate_clusters/', candidate_clusters, name='candidate_clusters'),

    path('dashboard/posting_list', recruiter_dashboard_posting_list, name="recruiter_dashboard_posting_list"),

    path('job_posting/add/', job_posting_add, name='job_posting_add'),
    path('job_posting/<str:jp_id>/', job_posting_details, name="job_posting_details"),

    # path('job_posting/initial_selection_stage/<str:jp_id>/', job_posting_initial_selection, name="job_posting_initial_selection"),
    # path('job_posting/prepare_invitations/<str:jp_id>/', job_posting_prepare_invitations, name='prepare_invitations'),

    path('job_posting/debug', candidate_debug, name="candidate_debug"),
    path('job_posting/candidate_status_update/<int:pk>/', candidate_status_update, name="candidate_status_update"),

    # path('job_posting/invitation_list/<str:jp_id>/', job_posting_invitation_list, name="invitation_list"),
    # path('job_posting/group_interview_list/<str:jp_id>/', job_posting_group_interview_list, name="group_interview_list"),

    path('job_posting/action/<str:jp_id>/', job_posting_action, name="job_posting_action"),
    path('job_posting/delete/<str:jp_id>', job_posting_delete, name="job_posting_delete"),
    path('job_posting/update/<str:jp_id>', job_posting_update, name="job_posting_update"),
    path('job_posting/candidate_status/<str:jp_id>/<int:pk>', candidate_status, name="candidate_status"),
    path('job_posting/candidate_discard/<str:jp_id>/<int:pk>', candidate_discard, name="candidate_discard"),
    path('job_posting/group_interview_debrief/<str:jp_id>', group_interview_debrief, name="group_interview_debrief"),
    path('job_posting/register_candidate_evaluation/<str:jp_id>/<int:pk>', register_candidate_evaluation, name="register_candidate_evaluation"),
    path('job_posting/message_templates_configuration/<str:jp_id>', message_templates_configuration, name="message_templates_configuration"),
    path('job_posting/register_one_to_one/<str:jp_id>/<int:pk>', register_one_to_one, name="register_one_to_one"),
    path('job_posting/stats/<str:jp_id>', job_posting_statistics, name="job_posting_statistics"),
    path('candidate/search/', candidate_search, name='candidate_search'),
    path('candidate/add/', candidate_add, name='candidate_add'),
    path('', recruiter, name='app'),


]
