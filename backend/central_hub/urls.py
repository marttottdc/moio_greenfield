from django.urls import path, include
from central_hub import views

# from central_hub.views import SignupView

urlpatterns = [

    # Moio Platform Landing page
    path('', views.moio, name="moio"),

    # Moio Platform CRM Home
    path('home/', views.home, name="home"),
    path('experience/', views.experience, name="experience"),
    path('blocks/<slug:group>/', views.content_blocks, name="portal_blocks"),

    path('health/', views.health_check, name='health_check'),
    path('user_detail/', views.UserDetailView.as_view(), name="user_detail"),
    path('user/list', views.user_list, name="user_list"),
    path('manager/add/', views.add_tenant, name='add_tenant'),
    path('configure_tenant/', views.configure_tenant, name='configure_tenant'),
    path('administration/tenants/', views.admin_tenants, name='admin_tenants'),
    path('administration/users/', views.admin_users, name='admin_users'),
    path('administration/tenants/add', views.add_tenant, name='add_tenant'),

    path('sse_stream/', views.sse_stream, name='sse_stream'),
    path('configuration/openai', views.configure_openai, name="configure_openai"),
    path('configuration/assistant', views.assistant_configuration, name="configure_assistant"),
    path('configuration/assistant/<str:assistant_id>', views.configure_assistant, name="edit_assistant"),

    path('configuration/assistant/', views.configure_assistant, name="create_assistant"),
    path('configuration/agent', views.agent_configuration_panel, name="agent_configuration_panel"),
    path('configuration/agent/<str:id>', views.configure_agent, name="edit_agent"),
    path('configuration/agent', views.configure_agent, name="create_agent"),

    path("settings/", views.settings, name="settings"),

    path("update_settings/", views.update_settings, name="update_settings"),
    path("configuration/<str:state>", views.settings, name="configuration_response_w_state"),
    path('configuration/waba/', views.configure_whatsapp_business, name="configure_whatsapp_business"),

    path("fb_oauth_callback/", views.facebook_oauth_callback_handler, name="facebook_oauth_callback_handler"),
    path("fb_registration/", views.confirm_waba_configuration, name="confirm_waba_configuration"),
    path("fb_revoke/", views.facebook_revoke_access, name="facebook_revoke_access"),
    path("fb_data_removal", views.facebook_data_removal, name="facebook_data_removal"),

    path("ig_oauth_callback/", views.instagram_oauth_callback_handler, name="instagram_oauth_callback_handler"),

    # Admin Console URLs
    path('admin-console/', views.admin_console, name='admin_console'),
    path('admin/tenant/form/', views.admin_tenant_form, name='admin_tenant_form'),
    path('admin/tenant/<int:tenant_id>/edit/', views.admin_tenant_edit, name='admin_tenant_edit'),
    path('admin/tenant/<int:tenant_id>/toggle/', views.admin_tenant_toggle, name='admin_tenant_toggle'),
    path('admin/system-config/', views.admin_system_config, name='admin_system_config'),


]

