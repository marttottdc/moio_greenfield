from django.urls import path

from . import views
from .api_schedule_views import FlowScheduleViewSet
from .api_event_views import EventDefinitionViewSet, EventLogViewSet
from .api_scheduled_tasks_views import ScheduledTaskViewSet, TaskExecutionViewSet

app_name = "flows_api"

schedule_list = FlowScheduleViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
schedule_detail = FlowScheduleViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'delete': 'destroy',
})
schedule_toggle = FlowScheduleViewSet.as_view({
    'post': 'toggle',
})

event_definition_list = EventDefinitionViewSet.as_view({
    'get': 'list',
})
event_definition_detail = EventDefinitionViewSet.as_view({
    'get': 'retrieve',
})

event_log_list = EventLogViewSet.as_view({
    'get': 'list',
})
event_log_detail = EventLogViewSet.as_view({
    'get': 'retrieve',
})

scheduled_task_list = ScheduledTaskViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
scheduled_task_detail = ScheduledTaskViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'delete': 'destroy',
})
scheduled_task_toggle = ScheduledTaskViewSet.as_view({
    'post': 'toggle',
})
scheduled_task_run_now = ScheduledTaskViewSet.as_view({
    'post': 'run_now',
})
scheduled_task_executions = ScheduledTaskViewSet.as_view({
    'get': 'executions',
})
scheduled_task_available_tasks = ScheduledTaskViewSet.as_view({
    'get': 'available_tasks',
})

task_execution_list = TaskExecutionViewSet.as_view({
    'get': 'list',
})
task_execution_detail = TaskExecutionViewSet.as_view({
    'get': 'retrieve',
})
task_execution_celery_status = TaskExecutionViewSet.as_view({
    'get': 'celery_status',
})
task_execution_running = TaskExecutionViewSet.as_view({
    'get': 'running',
})
task_execution_stats = TaskExecutionViewSet.as_view({
    'get': 'stats',
})

urlpatterns = [
    path("", views.api_flow_list, name="api_flow_list"),
    path("definitions/", views.api_flow_node_definitions, name="api_flow_node_definitions"),
    path("executions/", views.api_all_executions, name="api_all_executions"),
    path("executions/running/", views.api_running_executions, name="api_running_executions"),
    path("executions/<uuid:execution_id>/messages/", views.api_execution_messages, name="api_execution_messages"),
    path("whatsapp-logs/", views.api_whatsapp_logs_by_execution, name="api_whatsapp_logs_by_execution"),
    path("<uuid:flow_id>/", views.api_flow_detail, name="api_flow_detail"),
    path("<uuid:flow_id>/save/", views.api_flow_save, name="api_flow_save"),
    path("<uuid:flow_id>/validate/", views.api_flow_validate, name="api_flow_validate"),
    path(
        "<uuid:flow_id>/preview/",
        views.api_flow_preview,
        name="api_flow_preview",
    ),
    path(
        "<uuid:flow_id>/preview/<uuid:run_id>/",
        views.api_flow_preview_status,
        name="api_flow_preview_status",
    ),
    path(
        "<uuid:flow_id>/versions/<uuid:version_id>/arm/",
        views.api_flow_preview_arm,
        name="api_flow_preview_arm",
    ),
    path(
        "<uuid:flow_id>/versions/<uuid:version_id>/disarm/",
        views.api_flow_preview_disarm,
        name="api_flow_preview_disarm",
    ),
    path(
        "<uuid:flow_id>/new-version/",
        views.api_flow_new_version,
        name="api_flow_new_version",
    ),
    path(
        "<uuid:flow_id>/versions/",
        views.api_flow_versions,
        name="api_flow_versions",
    ),
    path(
        "<uuid:flow_id>/versions/<uuid:version_id>/",
        views.api_flow_version_detail,
        name="api_flow_version_detail",
    ),
    path(
        "<uuid:flow_id>/versions/<uuid:version_id>/publish/",
        views.api_flow_version_publish,
        name="api_flow_version_publish",
    ),
    path(
        "<uuid:flow_id>/versions/<uuid:version_id>/archive/",
        views.api_flow_version_archive,
        name="api_flow_version_archive",
    ),
    path(
        "<uuid:flow_id>/versions/<uuid:version_id>/restore/",
        views.api_flow_version_restore,
        name="api_flow_version_restore",
    ),
    path(
        "<uuid:flow_id>/toggle-active/",
        views.api_flow_toggle_active,
        name="api_flow_toggle_active",
    ),
    path(
        "<uuid:flow_id>/executions/",
        views.api_flow_executions,
        name="api_flow_executions",
    ),
    path(
        "<uuid:flow_id>/executions/stats/",
        views.api_flow_execution_stats,
        name="api_flow_execution_stats",
    ),
    path(
        "<uuid:flow_id>/executions/<uuid:execution_id>/",
        views.api_flow_execution_detail,
        name="api_flow_execution_detail",
    ),
    path("scripts/validate/", views.api_script_validate, name="api_script_validate"),

    # CRM registry for Flow CRM CRUD node
    path("crm/models/", views.api_flow_crm_models, name="api_flow_crm_models"),
    path("crm/<slug:slug>/", views.api_flow_crm_model_detail, name="api_flow_crm_model_detail"),
    
    path("<uuid:flow_pk>/schedules/", schedule_list, name="flow_schedule_list"),
    path("<uuid:flow_pk>/schedules/<uuid:pk>/", schedule_detail, name="flow_schedule_detail"),
    path("<uuid:flow_pk>/schedules/<uuid:pk>/toggle/", schedule_toggle, name="flow_schedule_toggle"),
    
    path("events/", event_definition_list, name="event_definition_list"),
    path("events/<uuid:pk>/", event_definition_detail, name="event_definition_detail"),
    
    path("event-logs/", event_log_list, name="event_log_list"),
    path("event-logs/<uuid:pk>/", event_log_detail, name="event_log_detail"),
    
    path("scheduled-tasks/", scheduled_task_list, name="scheduled_task_list"),
    path("scheduled-tasks/available-tasks/", scheduled_task_available_tasks, name="scheduled_task_available_tasks"),
    path("scheduled-tasks/<uuid:pk>/", scheduled_task_detail, name="scheduled_task_detail"),
    path("scheduled-tasks/<uuid:pk>/toggle/", scheduled_task_toggle, name="scheduled_task_toggle"),
    path("scheduled-tasks/<uuid:pk>/run-now/", scheduled_task_run_now, name="scheduled_task_run_now"),
    path("scheduled-tasks/<uuid:pk>/executions/", scheduled_task_executions, name="scheduled_task_executions"),
    
    # Task Executions API - query all executions across scheduled tasks
    path("task-executions/", task_execution_list, name="task_execution_list"),
    path("task-executions/running/", task_execution_running, name="task_execution_running"),
    path("task-executions/stats/", task_execution_stats, name="task_execution_stats"),
    path("task-executions/celery-status/<str:celery_task_id>/", task_execution_celery_status, name="task_execution_celery_status"),
    path("task-executions/<uuid:pk>/", task_execution_detail, name="task_execution_detail"),
]
