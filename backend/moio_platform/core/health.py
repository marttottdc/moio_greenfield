from django.db import connections
from django.db.utils import OperationalError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def probe_health(request):
    """
    Ultra-lightweight health endpoint for infra probes.

    Intentionally does not check external dependencies (DB, cache, etc.).
    """
    return Response({"status": "ok"}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Return a lightweight status report for the backend."""

    checks = {"database": "unknown"}
    overall_status = status.HTTP_200_OK

    try:
        connection = connections["default"]
        # ``cursor`` will raise an ``OperationalError`` if the DB is unreachable.
        with connection.cursor():
            checks["database"] = "ok"
    except OperationalError:
        checks["database"] = "unreachable"
        overall_status = status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "status": "ok" if overall_status == status.HTTP_200_OK else "degraded",
        "checks": checks,
        "suggested_additional_checks": [
            "cache_backend",
            "message_broker",
            "third_party_integrations",
        ],
    }

    return Response(payload, status=overall_status)
