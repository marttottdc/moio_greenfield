# middleware.py
from django.shortcuts import redirect
from django.conf import settings


class HTMXLoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.htmx and response.status_code == 302
                and response['Location'] == settings.LOGIN_URL):
            response.status_code = 401  # Let HTMX handle it in frontend
        return response