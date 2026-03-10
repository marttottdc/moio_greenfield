from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from central_hub.models import TenantScopedModel, Tenant


class ExternalAccount(TenantScopedModel):
    PROVIDER_CHOICES = [
        ("google", "google"),
        ("microsoft", "microsoft"),
        ("imap", "imap"),
    ]
    OWNERSHIP_CHOICES = [
        ("tenant", "tenant"),
        ("user", "user"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    ownership = models.CharField(max_length=20, choices=OWNERSHIP_CHOICES)

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="integration_external_accounts",
    )

    owner_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="integration_external_account",
    )

    email_address = models.EmailField()
    credentials = models.JSONField()
    state = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "integration_external_account"
        constraints = [
            models.UniqueConstraint(
                fields=["owner_user"],
                condition=Q(ownership="user"),
                name="external_account_unique_user",
            ),
            models.CheckConstraint(
                check=Q(ownership="tenant", owner_user__isnull=True) | ~Q(ownership="tenant"),
                name="external_account_tenant_owner_null",
            ),
            models.CheckConstraint(
                check=Q(ownership="user", owner_user__isnull=False) | ~Q(ownership="user"),
                name="external_account_user_owner_present",
            ),
        ]

    def clean(self):
        errors = {}

        if self.ownership == "tenant":
            if self.owner_user_id is not None:
                errors["owner_user"] = "Tenant-owned accounts must not have an owner_user."
        elif self.ownership == "user":
            if not self.owner_user_id:
                errors["owner_user"] = "User-owned accounts require owner_user."
            else:
                if self.owner_user.email.lower() != (self.email_address or "").lower():
                    errors["email_address"] = "User account email must match owner_user.email."
                owner_tenant = getattr(self.owner_user, "tenant_id", None)
                if owner_tenant and self.tenant_id and owner_tenant != self.tenant_id:
                    errors["owner_user"] = "Owner user must belong to the same tenant."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        scope = self.ownership
        owner = self.owner_user.email if self.owner_user_id else "tenant"
        return f"{self.provider}:{self.email_address} ({scope} - {owner})"


class EmailAccount(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="integration_email_accounts",
    )
    external_account = models.ForeignKey(
        ExternalAccount,
        on_delete=models.CASCADE,
        related_name="email_accounts",
    )
    inbox = models.CharField(max_length=255, default="INBOX")

    class Meta:
        db_table = "integration_email_account"

    def __str__(self) -> str:
        return f"EmailAccount<{self.external_account.provider}:{self.inbox}>"


class CalendarAccount(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="integration_calendar_accounts",
    )
    external_account = models.ForeignKey(
        ExternalAccount,
        on_delete=models.CASCADE,
        related_name="calendar_accounts",
    )
    calendar_id = models.CharField(max_length=255, default="primary")

    class Meta:
        db_table = "integration_calendar_account"

    def __str__(self) -> str:
        return f"CalendarAccount<{self.external_account.provider}:{self.calendar_id}>"

