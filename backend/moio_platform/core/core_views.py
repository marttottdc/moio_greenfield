from django.http import JsonResponse


def render_error(request, status_code, template_name, message=None):
    """Always return JSON errors; HTML pages are retired from the active backend."""
    context = {
        "status_code": status_code,
        "message": message or "An unexpected error occurred.",
    }
    return JsonResponse(context, status=status_code)


def handler400(request, exception=None):
    return render_error(request, 400, "400.html", "Bad Request")


def handler403(request, exception=None):
    return render_error(request, 403, "403.html", "Forbidden")


def handler404(request, exception=None):
    return render_error(request, 404, "404.html", "Page Not Found")


def handler500(request):
    return render_error(request, 500, "500.html", "Server Error")
