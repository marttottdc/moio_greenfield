from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from security.authentication import ServiceJWTAuthentication
from central_hub.rbac import require_role, user_has_role, RequireHumanUser
from central_hub.integrations.v1.models import CalendarAccount
from central_hub.integrations.v1.serializers import CalendarAccountSerializer, CalendarEventSerializer, CreateCalendarEventSerializer
from central_hub.integrations.v1.services.accounts import visible_calendar_accounts
from central_hub.integrations.v1.utils import api_error
from central_hub.integrations.v1.services import calendar_service


AUTH_CLASSES = [
    CsrfExemptSessionAuthentication,
    TenantJWTAAuthentication,
    ServiceJWTAuthentication,
]


class IntegrationCalendarBaseView(APIView):
    authentication_classes = AUTH_CLASSES
    permission_classes = [RequireHumanUser]


class CalendarAccountsView(IntegrationCalendarBaseView):
    def get(self, request):
        qs = visible_calendar_accounts(request.user).select_related("external_account")
        if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
            qs = qs.filter(external_account__ownership="user", external_account__owner_user=request.user)
        serializer = CalendarAccountSerializer(qs, many=True)
        return Response(serializer.data)


class CalendarAccountDetailView(IntegrationCalendarBaseView):
    def get(self, request, pk):
        account = get_object_or_404(
            CalendarAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can view this account."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        return Response(CalendarAccountSerializer(account).data)

    def delete(self, request, pk):
        account = get_object_or_404(
            CalendarAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can disconnect tenant accounts."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        account.external_account.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CalendarFlowAccountsView(IntegrationCalendarBaseView):
    def get(self, request):
        scope = request.query_params.get("scope", "tenant")
        tenant = getattr(request.user, "tenant", None)
        if not tenant:
            return Response(api_error("permission_denied", "Tenant required"), status=403)

        if scope == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can list tenant accounts."), status=403)
            qs = CalendarAccount.objects.filter(
                tenant=tenant,
                external_account__ownership="tenant",
                external_account__is_active=True,
            ).select_related("external_account")
        else:
            qs = CalendarAccount.objects.filter(
                tenant=tenant,
                external_account__ownership="user",
                external_account__owner_user=request.user,
                external_account__is_active=True,
            ).select_related("external_account")
        return Response(CalendarAccountSerializer(qs, many=True).data)


class CalendarAccountHealthView(IntegrationCalendarBaseView):
    def get(self, request, pk):
        account = get_object_or_404(CalendarAccount.objects.select_related("external_account"), id=pk)
        return Response({"status": "ok", "provider": account.external_account.provider})


class CalendarEventsListView(IntegrationCalendarBaseView):
    def get(self, request, pk):
        account = get_object_or_404(
            CalendarAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can view tenant events."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        cursor = request.query_params.get("cursor")
        page_size = int(request.query_params.get("page_size", "20"))
        items, next_cursor = calendar_service.list_events(account, start=start, end=end, cursor=cursor, page_size=page_size)
        return Response({"items": CalendarEventSerializer(items, many=True).data, "next_cursor": next_cursor})

    def post(self, request, pk):
        account = get_object_or_404(
            CalendarAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can create tenant events."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        serializer = CreateCalendarEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event_id = calendar_service.create_event(account, serializer.validated_data)
        return Response({"ok": True, "id": event_id}, status=status.HTTP_201_CREATED)


class CalendarEventDetailView(IntegrationCalendarBaseView):
    def get(self, request, pk, event_id):
        account = get_object_or_404(
            CalendarAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can view tenant events."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        ev = calendar_service.get_event(account, event_id)
        return Response(CalendarEventSerializer(ev).data)

    def patch(self, request, pk, event_id):
        account = get_object_or_404(
            CalendarAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can update tenant events."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        serializer = CreateCalendarEventSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ev = calendar_service.update_event(account, event_id, serializer.validated_data)
        return Response(CalendarEventSerializer(ev).data)

    def delete(self, request, pk, event_id):
        account = get_object_or_404(
            CalendarAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can delete tenant events."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        calendar_service.delete_event(account, event_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

