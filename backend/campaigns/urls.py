from django.urls import path
from campaigns.views import campaigns as campaign_views, audiences as audiences_views

app_name = 'campaigns'

urlpatterns = [
    # Main campaigns page
    path('', campaign_views.campaigns_view, name='campaigns'),

    # Campaign CRUD
    path('campaign/new/', campaign_views.campaign_add, name='campaign-new'),
    path('campaign/<uuid:pk>/edit/', campaign_views.campaign_edit, name='campaign-edit'),
    path('campaign/<uuid:pk>/configure/', campaign_views.campaign_configure, name='campaign-configure'),


    path('campaign/<uuid:pk>/delete/', campaign_views.campaign_delete, name='campaign-delete'),
    path('campaign/<uuid:pk>/duplicate/', campaign_views.campaign_duplicate, name='campaign-duplicate'),
    path('campaign/list/', campaign_views.campaign_list, name='campaign-list'),
    path('campaign/kpis/', campaign_views.refresh_kpis, name='refresh-kpis'),
    path('campaign/<uuid:pk>/import_data/', campaign_views.import_data, name='campaign-import-data'),
    path('campaign/import_data/', campaign_views.import_data, name='campaign-import-data'),
    path('campaign/data_mapper/', campaign_views.data_mapper, name='campaign-data_mapper'),
    path('campaign/<uuid:pk>/data_mapper/', campaign_views.data_mapper, name='campaign-data_mapper-pk'),


    path('campaign/<str:pk>/schedule/', campaign_views.campaign_scheduler, name='campaign-scheduler'),
    path('campaign/schedule/', campaign_views.campaign_scheduler, name='campaign-set-schedule'),

    path('campaign/<str:job_id>/monitor', campaign_views.campaign_task_monitor, name='campaign-task-monitor'),

    # Analytics tab endpoints
    path('analytics/', campaign_views.campaign_analytics, name='analytics'),


    path("audiences/create-basics/", audiences_views.audience_create_basics, name="audience-create"),
    path("audiences/<uuid:pk>/configure/", audiences_views.audience_configure, name="audience-configure"),
    path("audiences/<uuid:pk>/dynamic/save/", audiences_views.audience_dynamic_save, name="audience-dynamic-save"),
    path("audiences/<uuid:pk>/static/finalize/", audiences_views.audience_static_finalize, name="audience-static-finalize"),
    path("audiences/<uuid:pk>/delete/", audiences_views.audience_delete, name="audience-delete"),
    path('audiences/list/', audiences_views.audience_list, name='audience-list'),
    path("audiences/<uuid:pk>/autosave/",audiences_views.audience_autosave,name="audience-autosave"),
    path("audiences/condition-delete/", audiences_views.condition_delete, name="condition-delete"),
    path("audiences/<uuid:pk>/assisted/preview/", audiences_views.audience_assisted_preview, name="audience-assisted-preview"),
    path("audiences/<uuid:pk>/assisted/save/", audiences_views.audience_assisted_save, name="audience-assisted-save"),



    # HTMX endpoints
    path('htmx/condition-row/', audiences_views.condition_row, name='condition-row'),
    path('htmx/preview-count/', audiences_views.preview_count, name='preview-count'),
    path('htmx/search-contacts/', audiences_views.search_contacts, name='search-contacts'),
    path('htmx/toggle-contact/', audiences_views.toggle_contact, name='toggle-contact'),
    path('htmx/audience-contacts/<uuid:audience_id>/', audiences_views.audience_contacts, name='audience-contacts'),


    # WhatsApp Templates tab
    path('whatsapp-templates/', campaign_views.whatsapp_templates_tab, name='whatsapp-templates'),
    path('whatsapp-templates-selector/', campaign_views.load_whatsapp_templates, name='whatsapp-selector'),
    path('whatsapp-templates/<template_id>/detail/', campaign_views.whatsapp_template_details, name="whatsapp_template_details"),

    path('campaign/<uuid:pk>/msg_logs/', campaign_views.whatsapp_log, name="whatsapp-log"),


]