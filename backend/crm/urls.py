from django.urls import path

from crm.views import woocommerce_webhook_receiver, branch_list, \
    add_customer, update_customer, add_order, \
    ticket_add, ticket_list, ticket_update, ticket_comment_add, ticket_kpis_dashboard, ticket_details, orders_list, \
    customers_list, crm_dashboard_kpis, deliveries, deliveries_tracking, import_ecommerce_orders, \
    product_list, product_add, generic_webhook_receiver, products_import, product_tags, ticket_details_public

from crm import views

app_name = "crm"

urlpatterns = [

    path('deals/', views.deals, name='deals'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Contact Management

    path('contacts/', views.contact_paged_list, name='contacts'),
    path('contact/add/', views.contact_add, name='contact_add'),
    path('contact/update/', views.contact_update, name='contact_update'),

    path('deals/', views.deals, name='deals'),
    path('tasks/', views.tasks, name='tasks'),

    # path('settings/', views.settings, name='settings'),

    path('products/', views.products, name='products'),
    path('tickets/', views.tickets, name='tickets'),

    ##########################
    #
    #   COMMS
    #
    ##########################

    path('comms/', views.communications, name='communications'),
    path('sessions_list', views.sessions_list, name='sessions_list'),

    ####################
    #
    # LEGACY SCREENS
    #
    ###################
    path('import_data/', views.import_data, name="import_data"),

    path("shipments/<str:tracking_code>", deliveries_tracking, name="deliveries_tracking"),
    path("shipments/", deliveries, name="shipment"),

    path('branches/', branch_list, name="branch_list"),

    path('customers/', customers_list, name="customers_list"),
    path('customers/add', add_customer, name="add_customer"),
    path('customer/update', update_customer, name="update_customer"),

    path('orders/add', add_order, name="add_order"),
    path('orders/', orders_list, name="orders"),

    path('products/', product_list, name="product_list"),
    path('product_tags/<str:product_id>/', product_tags, name="product_tags"),
    path('products/add', product_add, name="product_add"),
    path('products/import',products_import, name="products_import"),

    path('tickets/add', ticket_add, name="ticket_add"),
    path('tickets/update/<str:id>', ticket_update, name="ticket_update"),
    path('tickets/ticket_list', ticket_list, name="ticket_list"),

    path('tickets/<uuid:id>/commment_add/', ticket_comment_add, name="ticket_comment_add"),
    path('tickets/ticket_kpis_dashboard', ticket_kpis_dashboard, name="ticket_kpis_dashboard"),
    path('tickets/details/<str:id>', ticket_details, name="ticket_details"),
    path('tickets/public/<str:id>', ticket_details_public, name="tickets_details_public"),
    path('tickets/<uuid:id>/status_change/', views.ticket_status_change, name="ticket_status_change"),

    # path('contacts/', views.contacts, name='contacts'),
    # path('contacts/', views.contact_paged_list, name='contacts'),

    # path('contacts_list', views.contact_paged_list, name='contact_paged_list'),

    # path('dashboard/', crm_dashboard, name="dashboard"),
    path('dashboard_kpis/', crm_dashboard_kpis, name="dashboard_kpi"),
    path('import_ecommerce_orders/', import_ecommerce_orders, name="import_ecommerce_orders"),

    # Webhook Configuration Management
    path('webhook-config/', views.webhook_config_list, name="webhook_config_list"),
    path('webhook-config/add/', views.webhook_config_add, name="webhook_config_add"),
    path('webhook-config/edit/<str:webhook_id>/', views.webhook_config_edit, name="webhook_config_edit"),
    path('webhook-config/delete/<str:webhook_id>/', views.webhook_config_delete, name="webhook_config_delete"),
    path('webhooks/<str:webhook_id>/', generic_webhook_receiver, name="generic_webhook_receiver"),

    # AI Agent Configuration Management
    path('agent-config/', views.agent_config_list, name="agent_config_list"),
    path('agent-config/add/', views.agent_config_add, name="agent_config_add"),
    path('agent-config/edit/<str:agent_id>/', views.agent_config_edit, name="agent_config_edit"),
    path('agent-config/delete/<str:agent_id>/', views.agent_config_delete, name="agent_config_delete"),

    path("deal-move-stage/", views.deals_move_stage, name="deals_move_stage"),

    path("payment/", views.submit_payment_form, name="submit_payment_form"),
    path("faces/", views.face_detections, name="face_detections"),
    path("face_search/", views.face_search, name="face_search"),
    path("faces/detail/", views.face_page, name="face_page"),

]