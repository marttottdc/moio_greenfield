from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError

from central_hub.integrations.v1.models import ExternalAccount, EmailAccount, CalendarAccount


EMAIL_PROVIDERS = {"google", "microsoft", "imap"}
CALENDAR_PROVIDERS = {"google", "microsoft"}


def ensure_user_slot_available(owner_user) -> None:
    exists = ExternalAccount.objects.filter(ownership="user", owner_user=owner_user).exists()
    if exists:
        raise ValidationError({"owner_user": "User already has a connected account."})


@transaction.atomic
def create_external_accounts(
    *,
    tenant,
    provider: str,
    ownership: str,
    email_address: str,
    credentials: dict,
    state: dict | None = None,
    owner_user=None,
) -> ExternalAccount:
    """
    Create ExternalAccount and child capability accounts based on provider.
    """
    if ownership == "user":
        ensure_user_slot_available(owner_user)

    external = ExternalAccount.objects.create(
        tenant=tenant,
        provider=provider,
        ownership=ownership,
        owner_user=owner_user,
        email_address=email_address,
        credentials=credentials,
        state=state or {},
    )

    if provider in EMAIL_PROVIDERS:
        EmailAccount.objects.create(tenant=tenant, external_account=external)

    if provider in CALENDAR_PROVIDERS:
        CalendarAccount.objects.create(tenant=tenant, external_account=external)

    return external


def visible_email_accounts(user):
    """
    Email accounts visible to the current user:
    - Tenant-owned if user is tenant_admin/superuser
    - User-owned belonging to the user
    """
    qs = EmailAccount.objects.select_related("external_account", "external_account__owner_user")
    tenant = getattr(user, "tenant", None)
    if tenant:
        qs = qs.filter(tenant=tenant)
    if getattr(user, "is_superuser", False):
        return qs

    # tenant_admin check will be enforced by caller (require_role)
    user_owned = qs.filter(external_account__ownership="user", external_account__owner_user=user)
    return user_owned | qs.filter(
        external_account__ownership="tenant",
    )


def visible_calendar_accounts(user):
    qs = CalendarAccount.objects.select_related("external_account", "external_account__owner_user")
    tenant = getattr(user, "tenant", None)
    if tenant:
        qs = qs.filter(tenant=tenant)
    if getattr(user, "is_superuser", False):
        return qs
    user_owned = qs.filter(external_account__ownership="user", external_account__owner_user=user)
    return user_owned | qs.filter(
        external_account__ownership="tenant",
    )

