from django.urls import path
from . import views
app_name = "flows"

urlpatterns = [
    path("", views.flow_list, name="list"),
    path("create/", views.flow_create, name="create"),

    # Legacy route kept for backward compatibility (redirects to React builder).
    # NOTE: The canonical builder name is `builder_react`; do not use `builder`.
    path("<uuid:flow_id>/builder/", views.flow_builder, name="builder_legacy_redirect"),
    path("<uuid:flow_id>/builder/react/", views.flow_builder_react, name="builder_react"),
    path("<uuid:flow_id>/run/manual/", views.manual_run, name="manual_run"),
    path("<uuid:flow_id>/preview/run/", views.preview, name="preview"),
    path("<uuid:flow_id>/publish/", views.publish, name="publish"),
    path("<uuid:flow_id>/toggle/", views.flow_toggle_active, name="toggle"),
    path("<uuid:flow_id>/whatsapp/templates/", views.whatsapp_templates, name="whatsapp_templates"),
    path("<uuid:flow_id>/webhooks/", views.flow_available_webhooks, name="available_webhooks",),

    # path("<uuid:flow_id>/builder/webhooks/", views.flow_builder_create_webhook, name="webhook_create",),
    # path("<uuid:flow_id>/export/", views.flow_export, name="export"),  # <- remove
    # path("<uuid:flow_id>/import/", views.flow_import, name="import"),  # (opcional) remove

    path("<uuid:flow_id>/save/", views.save, name="save"),
    path("<uuid:flow_id>/preview/stream/", views.preview_stream, name="preview_stream"),
    # Legacy node editor endpoints removed with the legacy builder.

    # API endpoints
    path("api/executions/running/", views.running_executions, name="running_executions"),

    # Script endpoints
    path("scripts/", views.script_list, name="script_list"),
    path("scripts/new/", views.script_builder, name="script_builder_new"),
    path("scripts/builder/", views.script_builder, name="script_builder"),

    path("scripts/validate/", views.script_validate, name="script_validate"),
    path("scripts/save/", views.script_save_draft, name="script_save_new"),

    path("scripts/publish/", views.script_publish, name="script_publish"),
    path("scripts/run/", views.script_run, name="script_run"),
    path("scripts/runs/<uuid:run_id>/stream/", views.script_log_stream, name="script_log_stream"),
]
