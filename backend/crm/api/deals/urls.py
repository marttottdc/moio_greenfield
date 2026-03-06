from django.urls import path

from crm.api.deals.views import (
    DealsView, DealDetailView, DealMoveStageView, DealCommentsView,
    PipelinesView, PipelineDetailView, PipelineStagesView,
    PipelineStageDetailView, PipelineCreateDefaultView
)

urlpatterns = [
    path("", DealsView.as_view(), name="deals-list"),
    path("<uuid:deal_id>/", DealDetailView.as_view(), name="deal-detail"),
    path("<uuid:deal_id>/move-stage/", DealMoveStageView.as_view(), name="deal-move-stage"),
    path("<uuid:deal_id>/comments/", DealCommentsView.as_view(), name="deal-comments"),

    path("pipelines/", PipelinesView.as_view(), name="pipelines-list"),
    path("pipelines/create-default/", PipelineCreateDefaultView.as_view(), name="pipeline-create-default"),
    path("pipelines/<uuid:pipeline_id>/", PipelineDetailView.as_view(), name="pipeline-detail"),
    path("pipelines/<uuid:pipeline_id>/stages/", PipelineStagesView.as_view(), name="pipeline-stages"),
    path("pipelines/<uuid:pipeline_id>/stages/<uuid:stage_id>/", PipelineStageDetailView.as_view(), name="pipeline-stage-detail"),
]
