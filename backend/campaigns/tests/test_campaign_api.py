import os
import uuid
from unittest import mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import django
django.setup()

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from campaigns.models import Audience, Campaign, Channel, Kind, Status
from central_hub.context_utils import current_tenant
from central_hub.models import Tenant


class CampaignApiTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.tenant = Tenant.objects.create(nombre="Tenant", domain="tenant.test")
        self.tenant_token = current_tenant.set(self.tenant)
        self.user = get_user_model().objects.create_user(
            username="user", email="user@test.com", password="pass"
        )
        self.client.force_authenticate(self.user)
        self.audience = Audience.objects.create(
            tenant=self.tenant, name="Audience", size=1
        )
        self.campaign = Campaign.objects.create(
            tenant=self.tenant,
            name="Campaign",
            description="Desc",
            channel=Channel.WHATSAPP,
            kind=Kind.ONE_SHOT,
            status=Status.DRAFT,
            audience=self.audience,
            config={},
        )

    def tearDown(self):
        current_tenant.reset(self.tenant_token)
        super().tearDown()

    def test_duplicate_campaign(self):
        self.campaign.config = {"message": {"whatsapp_template_id": "tmpl"}, "data_staging": "x"}
        self.campaign.save(update_fields=["config"])

        url = reverse("campaign-duplicate", args=[self.campaign.pk])
        response = self.client.post(url, format="json")

        assert response.status_code == 201
        assert Campaign.objects.count() == 2
        duplicated = Campaign.objects.exclude(id=self.campaign.id).first()
        assert duplicated.config.get("data_staging") is None
        assert duplicated.name.endswith("(copy)")

    def test_apply_mapping(self):
        url = reverse("campaign-config-mapping", args=[self.campaign.pk])
        payload = {
            "mapping": [
                {"template_var": "first", "target_field": "name", "type": "variable"}
            ],
            "contact_name_field": "fullname",
        }

        response = self.client.patch(url, payload, format="json")
        assert response.status_code == 200

        self.campaign.refresh_from_db()
        mapping = self.campaign.config.get("message", {}).get("map")
        assert mapping is not None
        assert any(item.get("template_var") == "contact_name" for item in mapping)

    @mock.patch("campaigns.api.views.campaign_config.fetch_whatsapp_template_requirements")
    def test_update_template(self, requirements_mock):
        requirements_mock.return_value = {"components": []}
        url = reverse("campaign-config-template", args=[self.campaign.pk])
        payload = {"template_id": "abc123"}

        response = self.client.patch(url, payload, format="json")
        assert response.status_code == 200

        self.campaign.refresh_from_db()
        assert (
            self.campaign.config.get("message", {}).get("whatsapp_template_id")
            == "abc123"
        )

    def test_update_schedule(self):
        url = reverse("campaign-schedule", args=[self.campaign.pk])
        date_value = timezone.now()
        payload = {"date": date_value.isoformat()}

        response = self.client.patch(url, payload, format="json")
        assert response.status_code == 200

        self.campaign.refresh_from_db()
        assert self.campaign.status == Status.SCHEDULED
        assert self.campaign.config.get("schedule", {}).get("date")

    @mock.patch("campaigns.core.service.execute_campaign")
    def test_launch_returns_job_ids(self, execute_mock):
        execute_mock.return_value = [mock.Mock(id=str(uuid.uuid4())) for _ in range(2)]
        url = reverse("campaign-launch", args=[self.campaign.pk])

        response = self.client.post(url, format="json")
        assert response.status_code == 200
        assert len(response.data.get("jobs")) == 2

    def test_delete_active_campaign_returns_409(self):
        """DELETE campaign with status=active must return 409 and not delete."""
        self.campaign.status = Status.ACTIVE
        self.campaign.save(update_fields=["status"])
        url = reverse("campaigns-api-detail", args=[self.campaign.pk])
        response = self.client.delete(url)
        assert response.status_code == 409
        assert response.data.get("error") == "cannot_delete_active"
        self.campaign.refresh_from_db()
        assert self.campaign.status == Status.ACTIVE

    def test_delete_draft_campaign_returns_204(self):
        """DELETE campaign with status=draft must succeed (204)."""
        assert self.campaign.status == Status.DRAFT
        url = reverse("campaigns-api-detail", args=[self.campaign.pk])
        response = self.client.delete(url)
        assert response.status_code == 204
        assert not Campaign.objects.filter(pk=self.campaign.pk).exists()
