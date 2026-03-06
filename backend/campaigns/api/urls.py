"""Router definitions for the campaigns API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from campaigns.api.views import (
    CampaignCrudViewSet,
    CampaignConfigViewSet,
    CampaignExecutionViewSet,
    AudienceViewSet,
    CampaignFlowViewSet,
    CampaignStreamView,
)

router = DefaultRouter()
router.register(r"campaigns", CampaignCrudViewSet, basename="campaigns-api")
router.register(r"audiences", AudienceViewSet, basename="audiences-api")

urlpatterns = [
    path("", include(router.urls)),

    # ---- Campaign Config (Legacy) ----
    path(
        "campaigns/<uuid:pk>/config/message/",
        CampaignConfigViewSet.as_view({"patch": "update_template"}),
        name="campaign-config-template",
    ),
    path(
        "campaigns/<uuid:pk>/config/defaults/",
        CampaignConfigViewSet.as_view({"patch": "update_defaults"}),
        name="campaign-config-defaults",
    ),
    path(
        "campaigns/<uuid:pk>/config/mapping/",
        CampaignConfigViewSet.as_view({"patch": "apply_mapping"}),
        name="campaign-config-mapping",
    ),
    path(
        "campaigns/<uuid:pk>/schedule/",
        CampaignConfigViewSet.as_view({"patch": "update_schedule"}),
        name="campaign-schedule",
    ),

    # ---- Campaign Execution (Legacy) ----
    path(
        "campaigns/<uuid:pk>/duplicate/",
        CampaignExecutionViewSet.as_view({"post": "duplicate"}),
        name="campaign-duplicate",
    ),
    path(
        "campaigns/<uuid:pk>/launch/",
        CampaignExecutionViewSet.as_view({"post": "launch"}),
        name="campaign-launch",
    ),
    path(
        "campaigns/<uuid:pk>/validate/",
        CampaignExecutionViewSet.as_view({"post": "validate_campaign"}),
        name="campaign-validate",
    ),
    path(
        "campaigns/<uuid:pk>/logs/",
        CampaignExecutionViewSet.as_view({"get": "logs"}),
        name="campaign-logs",
    ),
    path(
        "campaigns/<uuid:pk>/jobs/<str:job_id>/",
        CampaignExecutionViewSet.as_view({"get": "job_status"}),
        name="campaign-job-status",
    ),

    # ---- Campaign Flow V2 (FSM-based) ----
    path(
        "campaigns/<uuid:pk>/flow-state/",
        CampaignFlowViewSet.as_view({"get": "flow_state"}),
        name="campaign-flow-state",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/select-template/",
        CampaignFlowViewSet.as_view({"post": "select_template"}),
        name="campaign-transition-select-template",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/import-data/",
        CampaignFlowViewSet.as_view({"post": "import_data"}),
        name="campaign-transition-import-data",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/configure-mapping/",
        CampaignFlowViewSet.as_view({"post": "configure_mapping"}),
        name="campaign-transition-configure-mapping",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/set-audience/",
        CampaignFlowViewSet.as_view({"post": "set_audience"}),
        name="campaign-transition-set-audience",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/mark-ready/",
        CampaignFlowViewSet.as_view({"post": "mark_ready"}),
        name="campaign-transition-mark-ready",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/set-schedule/",
        CampaignFlowViewSet.as_view({"post": "set_schedule"}),
        name="campaign-transition-set-schedule",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/schedule-launch/",
        CampaignFlowViewSet.as_view({"post": "schedule_launch"}),
        name="campaign-transition-schedule-launch",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/launch-now/",
        CampaignFlowViewSet.as_view({"post": "launch_now"}),
        name="campaign-transition-launch-now",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/cancel-schedule/",
        CampaignFlowViewSet.as_view({"post": "cancel_schedule"}),
        name="campaign-transition-cancel-schedule",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/complete/",
        CampaignFlowViewSet.as_view({"post": "complete"}),
        name="campaign-transition-complete",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/cancel/",
        CampaignFlowViewSet.as_view({"post": "cancel"}),
        name="campaign-transition-cancel",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/rollback/",
        CampaignFlowViewSet.as_view({"post": "rollback"}),
        name="campaign-transition-rollback",
    ),
    path(
        "campaigns/<uuid:pk>/transitions/archive/",
        CampaignFlowViewSet.as_view({"post": "archive"}),
        name="campaign-transition-archive",
    ),

    # ---- SSE Streaming ----
    path(
        "campaigns/stream/",
        CampaignStreamView.as_view(),
        name="campaign-stream",
    ),
]