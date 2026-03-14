from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from central_hub.models import ProvisioningJob, Tenant


class SelfProvisionApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user_model = get_user_model()

    @patch("central_hub.tasks.create_tenant_for_provisioning.delay")
    def test_self_provision_returns_async_job_status(self, mocked_delay) -> None:
        response = self.client.post(
            "/api/v1/tenants/self-provision/",
            {
                "nombre": "Provisioned Tenant",
                "subdomain": "provisioned",
                "domain": "example.test",
                "email": "owner@example.test",
                "username": "owner@example.test",
                "password": "pass12345",
                "first_name": "Owner",
                "last_name": "Admin",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("task_id", response.data)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["current_stage"], "tenant_creation")
        self.assertIn("stages", response.data)

        job = ProvisioningJob.objects.get(pk=response.data["task_id"])
        self.assertEqual(job.requested_name, "Provisioned Tenant")
        self.assertEqual(job.requested_locale, "es")
        mocked_delay.assert_called_once()

    def test_provision_status_success_returns_tokens_for_created_user(self) -> None:
        tenant = Tenant.objects.create(
            nombre="Ready Tenant",
            domain="ready.test",
            subdomain="readytenant",
        )
        user = self.user_model.objects.create_user(
            email="ready@example.test",
            username="ready@example.test",
            password="pass12345",
            tenant=tenant,
            first_name="Ready",
            last_name="User",
        )
        job = ProvisioningJob.objects.create(
            requested_name=tenant.nombre,
            requested_email=user.email,
            requested_username=user.username,
            requested_subdomain=tenant.subdomain,
            requested_domain=tenant.domain,
            requested_locale="es",
            tenant=tenant,
            user=user,
            status="success",
            current_stage="primary_user_creation",
            stages={
                "tenant_creation": {"status": "success", "started_at": None, "finished_at": None, "error": ""},
                "tenant_seeding": {"status": "success", "started_at": None, "finished_at": None, "error": ""},
                "primary_user_creation": {"status": "success", "started_at": None, "finished_at": None, "error": ""},
            },
        )

        response = self.client.get(f"/api/v1/tenants/provision-status/{job.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["current_stage"], "primary_user_creation")
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
