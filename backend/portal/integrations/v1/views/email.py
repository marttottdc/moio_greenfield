from __future__ import annotations

import logging

from django.core import signing
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests

from portal.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from security.authentication import ServiceJWTAuthentication
from portal.rbac import require_role, user_has_role, RequireHumanUser
from portal.integrations.v1.models import EmailAccount, ExternalAccount
from portal.integrations.v1.serializers import (
    EmailAccountSerializer,
    ExternalAccountSerializer,
    EmailMessageSerializer,
    SendEmailSerializer,
)
from portal.integrations.v1.services.accounts import (
    create_external_accounts,
    ensure_user_slot_available,
    visible_email_accounts,
)
from portal.integrations.v1.services import token_service
from portal.integrations.v1.utils import api_error, build_callback_url
from portal.integrations.v1.services import email_service

logger = logging.getLogger(__name__)


AUTH_CLASSES = [
    CsrfExemptSessionAuthentication,
    TenantJWTAAuthentication,
    ServiceJWTAuthentication,
]


class IntegrationEmailBaseView(APIView):
    authentication_classes = AUTH_CLASSES
    permission_classes = [RequireHumanUser]

    def current_tenant(self):
        return getattr(self.request.user, "tenant", None)


class EmailAccountsView(IntegrationEmailBaseView):
    def get(self, request):
        qs = visible_email_accounts(request.user).select_related("external_account")
        if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
            qs = qs.filter(external_account__ownership="user", external_account__owner_user=request.user)
        serializer = EmailAccountSerializer(qs, many=True)
        return Response(serializer.data)


class EmailAccountDetailView(IntegrationEmailBaseView):
    def get_object(self, pk):
        return get_object_or_404(
            EmailAccount.objects.select_related("external_account", "external_account__owner_user"),
            id=pk,
        )

    def get(self, request, pk):
        account = self.get_object(pk)
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can view this account."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        return Response(EmailAccountSerializer(account).data)

    def delete(self, request, pk):
        account = self.get_object(pk)
        ext = account.external_account
        if ext.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can disconnect tenant accounts."), status=403)
        else:
            if ext.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        ext.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailAccountEnableView(IntegrationEmailBaseView):
    @require_role("tenant_admin")
    def post(self, request, pk):
        account = get_object_or_404(EmailAccount.objects.select_related("external_account"), id=pk)
        if account.external_account.ownership != "tenant":
            return Response(api_error("permission_denied", "Enable/disable allowed only for tenant accounts."), status=403)
        account.external_account.is_active = True
        account.external_account.save(update_fields=["is_active"])
        return Response({"ok": True})


class EmailAccountDisableView(IntegrationEmailBaseView):
    @require_role("tenant_admin")
    def post(self, request, pk):
        account = get_object_or_404(EmailAccount.objects.select_related("external_account"), id=pk)
        if account.external_account.ownership != "tenant":
            return Response(api_error("permission_denied", "Enable/disable allowed only for tenant accounts."), status=403)
        account.external_account.is_active = False
        account.external_account.save(update_fields=["is_active"])
        return Response({"ok": True})


class EmailFlowAccountsView(IntegrationEmailBaseView):
    def get(self, request):
        scope = request.query_params.get("scope", "tenant")
        tenant = getattr(request.user, "tenant", None)
        if not tenant:
            return Response(api_error("permission_denied", "Tenant required"), status=403)

        if scope == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can list tenant accounts."), status=403)
            qs = EmailAccount.objects.filter(
                tenant=tenant,
                external_account__ownership="tenant",
                external_account__is_active=True,
            ).select_related("external_account")
        else:
            qs = EmailAccount.objects.filter(
                tenant=tenant,
                external_account__ownership="user",
                external_account__owner_user=request.user,
                external_account__is_active=True,
            ).select_related("external_account")
        return Response(EmailAccountSerializer(qs, many=True).data)


class EmailAccountHealthView(IntegrationEmailBaseView):
    def get(self, request, pk):
        account = get_object_or_404(EmailAccount.objects.select_related("external_account"), id=pk)
        # Simple placeholder health check
        return Response({"status": "ok", "provider": account.external_account.provider})


class EmailOAuthStartView(IntegrationEmailBaseView):
    def post(self, request):
        provider = request.data.get("provider")
        ownership = request.data.get("ownership", "tenant")

        if provider not in {"google", "microsoft"}:
            return Response(api_error("invalid_provider", "Provider must be google or microsoft"), status=400)
        if ownership not in {"tenant", "user"}:
            return Response(api_error("invalid_ownership", "ownership must be tenant or user"), status=400)

        if ownership == "tenant" and not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
            return Response(api_error("permission_denied", "Only tenant admins can connect tenant accounts."), status=403)

        if ownership == "user":
            try:
                ensure_user_slot_available(request.user)
            except Exception as exc:
                return Response(api_error("account_exists", str(exc)), status=400)

        tenant = getattr(request.user, "tenant", None)
        state_payload = {
            "tenant_id": str(getattr(tenant, "id", "")),
            "user_id": str(getattr(request.user, "id", "")) if ownership == "user" else None,
            "ownership": ownership,
            "provider": provider,
        }
        state = signing.dumps(state_payload, salt="integrations-v1-oauth")
        redirect_uri = build_callback_url(provider)

        if provider == "google":
            authorize_url = token_service.google_authorize_url(redirect_uri, state)
        else:
            authorize_url = token_service.microsoft_authorize_url(redirect_uri, state)

        return Response({"authorize_url": authorize_url, "state": state})


class EmailOAuthCallbackView(APIView):
    authentication_classes = AUTH_CLASSES

    def get(self, request, provider: str):
        if provider not in {"google", "microsoft"}:
            return Response(api_error("invalid_provider", "Unsupported provider"), status=400)

        state_param = request.GET.get("state")
        code = request.GET.get("code")
        if not state_param or not code:
            return Response(api_error("invalid_request", "Missing code or state"), status=400)

        try:
            state = signing.loads(state_param, salt="integrations-v1-oauth")
        except Exception:
            return Response(api_error("invalid_state", "State could not be verified"), status=400)

        from portal.models import Tenant
        from django.contrib.auth import get_user_model

        tenant = Tenant.objects.filter(id=state.get("tenant_id")).first()
        owner_user = None
        if state.get("ownership") == "user":
            owner_user = get_user_model().objects.filter(id=state.get("user_id")).first()
            if not owner_user:
                return Response(api_error("invalid_state", "User not found"), status=400)

        redirect_uri = build_callback_url(provider)
        try:
            if provider == "google":
                credentials = token_service.google_exchange_code(code, redirect_uri)
                email_address = token_service.google_email_from_id_token(credentials.get("id_token"))
                if not email_address:
                    # best-effort: fallback to tokeninfo
                    resp = requests.get(
                        "https://www.googleapis.com/oauth2/v3/userinfo",
                        headers={"Authorization": f"Bearer {credentials.get('access_token')}"},
                        timeout=20,
                    )
                    email_address = resp.json().get("email")
            else:
                credentials = token_service.microsoft_exchange_code(code, redirect_uri)
                profile = token_service.microsoft_get_profile(credentials.get("access_token"))
                email_address = profile.get("mail") or profile.get("userPrincipalName")
        except Exception as exc:
            logger.exception("OAuth callback failed")
            return Response(api_error("oauth_failed", str(exc)), status=400)

        if not email_address:
            return Response(api_error("profile_missing", "Could not resolve account email"), status=400)

        external = create_external_accounts(
            tenant=tenant,
            provider=provider,
            ownership=state.get("ownership"),
            owner_user=owner_user,
            email_address=email_address,
            credentials=credentials,
            state={},
        )

        return Response({"ok": True, "account_id": str(external.id)})


class EmailImapConnectView(IntegrationEmailBaseView):
    def post(self, request):
        ownership = request.data.get("ownership", "tenant")
        email_address = request.data.get("email_address")
        username = request.data.get("username")
        password = request.data.get("password")
        host = request.data.get("host")
        port = request.data.get("port")
        use_ssl = request.data.get("use_ssl", True)

        if ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can connect tenant accounts."), status=403)
        else:
            try:
                ensure_user_slot_available(request.user)
            except Exception as exc:
                return Response(api_error("account_exists", str(exc)), status=400)

        if not all([email_address, username, password, host, port]):
            return Response(api_error("invalid_request", "Missing IMAP credentials"), status=400)

        tenant = getattr(request.user, "tenant", None)
        smtp_cfg = request.data.get("smtp") or {}
        external = create_external_accounts(
            tenant=tenant,
            provider="imap",
            ownership=ownership,
            owner_user=request.user if ownership == "user" else None,
            email_address=email_address,
            credentials={
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "use_ssl": use_ssl,
                "smtp": smtp_cfg,
            },
            state={"last_uid": None},
        )
        return Response({"ok": True, "account_id": str(external.id)}, status=201)


class EmailMessagesListView(IntegrationEmailBaseView):
    def get(self, request, pk):
        account = get_object_or_404(
            EmailAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can view tenant messages."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        cursor = request.query_params.get("cursor")
        page_size = int(request.query_params.get("page_size", "20"))
        items, next_cursor = email_service.list_messages(account, cursor=cursor, page_size=page_size)
        return Response({"items": EmailMessageSerializer(items, many=True).data, "next_cursor": next_cursor})


class EmailMessageDetailView(IntegrationEmailBaseView):
    def get(self, request, pk, message_id):
        account = get_object_or_404(
            EmailAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can view tenant messages."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        msg = email_service.get_message(account, message_id)
        return Response(EmailMessageSerializer(msg).data)

    def delete(self, request, pk, message_id):
        account = get_object_or_404(
            EmailAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can delete tenant messages."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        email_service.delete_message(account, message_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailSendView(IntegrationEmailBaseView):
    def post(self, request, pk):
        account = get_object_or_404(
            EmailAccount.objects.select_related("external_account", "external_account__owner_user"), id=pk
        )
        if account.external_account.ownership == "tenant":
            if not (request.user.is_superuser or user_has_role(request.user, "tenant_admin")):
                return Response(api_error("permission_denied", "Only tenant admins can send from tenant accounts."), status=403)
        else:
            if account.external_account.owner_user_id != request.user.id and not request.user.is_superuser:
                return Response(api_error("permission_denied", "Not your account."), status=403)
        serializer = SendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        msg_id = email_service.send_message(account, serializer.validated_data)
        return Response({"ok": True, "id": msg_id})

