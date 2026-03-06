from django.urls import path

from .api_script_views import api_script_detail, api_script_execute, api_scripts

urlpatterns = [
    path("", api_scripts, name="api_script_list"),
    path("<uuid:script_id>/", api_script_detail, name="api_script_detail"),
    path("execute/", api_script_execute, name="api_script_execute"),
]
