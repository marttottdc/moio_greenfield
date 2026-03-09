from django.urls import path

from .api_views import RobotRunViewSet, RobotSessionViewSet, RobotViewSet

robot_list = RobotViewSet.as_view({"get": "list", "post": "create"})
robot_detail = RobotViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
robot_trigger = RobotViewSet.as_view({"post": "trigger"})
robot_runs = RobotViewSet.as_view({"get": "runs"})
robot_events = RobotViewSet.as_view({"get": "events"})
robot_run_cancel_nested = RobotViewSet.as_view({"post": "cancel_run"})
robot_sessions = RobotViewSet.as_view({"get": "sessions"})
robot_memories = RobotViewSet.as_view({"get": "memories", "post": "memories"})
robot_contracts = RobotViewSet.as_view({"get": "contracts"})

run_list = RobotRunViewSet.as_view({"get": "list"})
run_detail = RobotRunViewSet.as_view({"get": "retrieve"})
run_cancel = RobotRunViewSet.as_view({"post": "cancel"})
run_events = RobotRunViewSet.as_view({"get": "events"})

session_list = RobotSessionViewSet.as_view({"get": "list"})
session_detail = RobotSessionViewSet.as_view({"get": "retrieve"})
session_intent_state = RobotSessionViewSet.as_view({"patch": "update_intent_state"})

urlpatterns = [
    path("", robot_list, name="robot_list"),
    path("<uuid:pk>/", robot_detail, name="robot_detail"),
    path("<uuid:pk>/trigger/", robot_trigger, name="robot_trigger"),
    path("<uuid:pk>/runs/", robot_runs, name="robot_runs"),
    path("<uuid:pk>/events/", robot_events, name="robot_events"),
    path("<uuid:pk>/sessions/", robot_sessions, name="robot_sessions"),
    path("<uuid:pk>/memories/", robot_memories, name="robot_memories"),
    path("<uuid:pk>/runs/<uuid:run_id>/cancel/", robot_run_cancel_nested, name="robot_run_cancel_nested"),
    path("contracts/", robot_contracts, name="robot_contracts"),
    path("runs/", run_list, name="robot_run_list"),
    path("runs/<uuid:pk>/", run_detail, name="robot_run_detail"),
    path("runs/<uuid:pk>/cancel/", run_cancel, name="robot_run_cancel"),
    path("runs/<uuid:pk>/events/", run_events, name="robot_run_events"),
    path("sessions/", session_list, name="robot_session_list"),
    path("sessions/<uuid:pk>/", session_detail, name="robot_session_detail"),
    path("sessions/<uuid:pk>/intent-state/", session_intent_state, name="robot_session_intent_state"),
]
