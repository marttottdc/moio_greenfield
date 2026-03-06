from django.urls import path

from chatbot.api import desktop_agent

app_name = "desktop_agent_api"

urlpatterns = [
    path("sessions/", desktop_agent.list_desktop_sessions, name="list_sessions"),
    path("sessions/<str:session_id>/", desktop_agent.get_session_history, name="session_history"),
    path("sessions/<str:session_id>/close/", desktop_agent.close_session, name="close_session"),
    path("status/", desktop_agent.get_agent_status, name="agent_status"),
    path("runtime/resources/", desktop_agent.get_runtime_resources, name="runtime_resources"),
    path("agents/", desktop_agent.list_available_agents, name="available_agents"),
    path("set-agent/", desktop_agent.set_user_agent, name="set_agent"),
]
