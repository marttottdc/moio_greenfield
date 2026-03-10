from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from crm.api.tests.utils import ensure_schema
from central_hub.models import Tenant
from central_hub.signals import (
    create_internal_contact,
    create_tenant_configurations,
    create_user_profile,
    seed_tenant_entitlements,
)

ensure_schema()


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class UsersApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(create_tenant_configurations, sender=Tenant)
        post_save.disconnect(seed_tenant_entitlements, sender=Tenant)
        cls._user_model = get_user_model()
        post_save.disconnect(create_internal_contact, sender=cls._user_model)
        post_save.disconnect(create_user_profile, sender=cls._user_model)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_user_profile, sender=cls._user_model)
        post_save.connect(create_internal_contact, sender=cls._user_model)
        post_save.connect(seed_tenant_entitlements, sender=Tenant)
        post_save.connect(create_tenant_configurations, sender=Tenant)
        super().tearDownClass()

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            nombre="Tenant A",
            domain="a.test",
            plan=Tenant.Plan.PRO,
            features={"crm_contacts_read": True, "users_manage": True},
            limits={"seats": 10},
        )
        self.tenant_b = Tenant.objects.create(
            nombre="Tenant B",
            domain="b.test",
            features={"crm_contacts_read": True},
            limits={"seats": 5},
        )

        self.tenant_admin = self._user_model.objects.create_user(
            email="admin@a.test",
            username="admin-a",
            password="pass1234",
            tenant=self.tenant_a,
        )
        group, _ = Group.objects.get_or_create(name="tenant_admin")
        self.tenant_admin.groups.add(group)

        self.regular_user = self._user_model.objects.create_user(
            email="user@a.test",
            username="user-a",
            password="pass1234",
            tenant=self.tenant_a,
        )

        self.other_tenant_user = self._user_model.objects.create_user(
            email="user@b.test",
            username="user-b",
            password="pass1234",
            tenant=self.tenant_b,
        )

    def test_tenant_admin_can_list_users_scoped_to_tenant(self):
        self.client.force_authenticate(self.tenant_admin)

        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = {item["email"] for item in response.data}
        self.assertIn(self.tenant_admin.email, emails)
        self.assertIn(self.regular_user.email, emails)
        self.assertNotIn(self.other_tenant_user.email, emails)

    def test_non_admin_cannot_list_users(self):
        self.client.force_authenticate(self.regular_user)

        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_admin_can_create_user_in_own_tenant(self):
        self.client.force_authenticate(self.tenant_admin)

        payload = {
            "email": "new@a.test",
            "username": "new-user-a",
            "first_name": "New",
            "last_name": "User",
            "phone": "+123",
            "password": "pass1234",
            "role": "member",
        }
        response = self.client.post("/api/v1/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["email"], "new@a.test")
        self.assertEqual(response.data["organization"]["id"], str(self.tenant_a.id))
        self.assertEqual(response.data["organization"]["primary_domain"], "a.test")
        self.assertIn("member", response.data["groups"])

        created = self._user_model.objects.get(email="new@a.test")
        self.assertEqual(created.tenant_id, self.tenant_a.id)

    def test_create_requires_password(self):
        self.client.force_authenticate(self.tenant_admin)

        payload = {
            "email": "nopass@a.test",
            "username": "no-pass",
            "role": "member",
        }
        response = self.client.post("/api/v1/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_tenant_admin_cannot_access_other_tenant_user(self):
        self.client.force_authenticate(self.tenant_admin)

        response = self.client.get(f"/api/v1/users/{self.other_tenant_user.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_delete_self(self):
        self.client.force_authenticate(self.tenant_admin)

        response = self.client.delete(f"/api/v1/users/{self.tenant_admin.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
