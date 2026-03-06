from django.db.models import Count, Max
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from crm.api.mixins import ProtectedAPIView
from crm.models import Ticket


@extend_schema(tags=["dashboard"])
class DashboardSummaryView(ProtectedAPIView):
    def get(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Response({"tickets": {"total": 0, "open": 0, "closed": 0}})

        tickets = Ticket.objects.filter(tenant=tenant)
        stats = tickets.aggregate(
            total=Count("id"),
            open=Count("id", filter=~Ticket.closed_states_q()),
            closed=Count("id", filter=Ticket.closed_states_q()),
            latest=Max("created"),
        )
        return Response({
            "tickets": {
                "total": stats.get("total", 0) or 0,
                "open": stats.get("open", 0) or 0,
                "closed": stats.get("closed", 0) or 0,
                "latest": stats.get("latest"),
            }
        })

