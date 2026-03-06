from django.urls import path

from chatbot.views import whatsapp_webhook_receiver, list_whatsapp_templates,\
    create_campaign, chatroom, sessions, conversation_detail, send_message, dashboard, dashboard_kpi, \
    self_assessments, assessment, app, facebook_flows_handler, instagram_webhook_receiver, messenger_webhook_receiver

from chatbot import views

app_name = "chatbot"

urlpatterns = [

    path('campaigns/', create_campaign, name="my_campaign"),
    path('chatroom/', chatroom, name="chatroom"),
    path('webhooks/whatsapp/', whatsapp_webhook_receiver, name="whatsapp_webhook_receiver"),
    path('webhooks/instagram/', instagram_webhook_receiver, name="instagram_webhook_receiver"),
    path('webhooks/messenger/', messenger_webhook_receiver, name="messenger_webhook_receiver"),
    path("sessions", sessions, name="sessions"),
    path("conversation/<str:session_id>/", conversation_detail, name="conversation_detail"),
    path("send_message/", send_message, name="send_message"),
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard_kpi/", dashboard_kpi, name="dashboard_kpi"),

    path('campaign/<str:campaign_id>/', self_assessments, name='self_assessment'),
    path('assessment/<str:campaign_id>/', assessment, name='assessment'),
    path('', app, name="app"),

    path('flows/', facebook_flows_handler, name="facebook_flows_handler"),
    path('wa-templates/', list_whatsapp_templates, name='wa_templates'),


    path('watemplates/', list_whatsapp_templates, name="list_whatsapp_templates"),

    path('wa-templates-for-campaigns/', views.wa_templates_for_campaigns, name='wa_templates_for_campaigns'),
    path('watemplatedetails/<template_id>', views.whatsapp_template_details, name="wa_template_details"),

    path('desktop_agent/', views.desktop_agent, name="desktop_agent"),
    path('flows/', views.flow_handler, name="flow_handler"),
]