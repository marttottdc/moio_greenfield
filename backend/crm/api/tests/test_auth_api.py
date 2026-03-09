from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from crm.api.tests.utils import ensure_schema
from portal.models import Tenant, UserApiKey
from portal.signals import create_internal_contact, create_tenant_configurations

ensure_schema()


def _login(client, username: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK, response.data
    return response.data


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class AuthApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(create_tenant_configurations, sender=Tenant)
        cls._user_model = get_user_model()
        post_save.disconnect(create_internal_contact, sender=cls._user_model)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_internal_contact, sender=cls._user_model)
        post_save.connect(create_tenant_configurations, sender=Tenant)
        super().tearDownClass()

    def setUp(self):
        self.tenant = Tenant.objects.create(nombre="Auth Tenant", domain="auth.test")
        self.user = self._user_model.objects.create_user(
            email="auth@example.com",
            username="auth-user",
            password="pass1234",
            tenant=self.tenant,
            first_name="Auth",
            last_name="User",
        )

    def test_login_returns_simplejwt_tokens(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": self.user.email, "password": "pass1234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(set(response.data.keys()), {"access", "refresh"})
        self.assertTrue(Token.objects.filter(user=self.user).exists())

    def test_invalid_credentials_return_error_envelope(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": self.user.email, "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"], "invalid_credentials")

    def test_refresh_rotates_tokens(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        first_access = login_data["access"]
        refresh_payload = {"refresh": login_data["refresh"]}

        refreshed = self.client.post("/api/v1/auth/refresh/", refresh_payload, format="json")
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertIn("access", refreshed.data)
        self.assertIn("refresh", refreshed.data)
        self.assertEqual(set(refreshed.data.keys()), {"access", "refresh"})
        self.assertNotEqual(refreshed.data["access"], first_access)
        self.assertNotEqual(refreshed.data["refresh"], login_data["refresh"])
        old_refresh = refresh_payload["refresh"]

        # Old refresh token is blacklisted after use.
        invalid_retry = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh": old_refresh},
            format="json",
        )
        self.assertEqual(invalid_retry.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(invalid_retry.data["error"], "invalid_refresh_token")

        # New refresh token works for next refresh.
        second_refresh = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh": refreshed.data["refresh"]},
            format="json",
        )
        self.assertEqual(second_refresh.status_code, status.HTTP_200_OK)
        self.assertIn("access", second_refresh.data)
        self.assertIn("refresh", second_refresh.data)

    def test_logout_revokes_token(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        token = login_data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Successfully logged out")

        me = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_profile_and_preferences(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        token = login_data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertIn("preferences", response.data)
        self.assertIn("organization", response.data)
        self.assertEqual(response.data["organization"]["primary_domain"], "auth.test")

    def test_create_api_key_returns_plain_key_once(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_data['access']}")
        response = self.client.post(
            "/api/v1/auth/api-key/",
            {"name": "My Integration"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("key", response.data)
        self.assertTrue(response.data["key"].startswith("moio_"))
        self.assertEqual(len(response.data["key"]), 5 + 32)  # moio_ + 32 chars
        self.assertIn("warning", response.data)
        self.assertTrue(UserApiKey.objects.filter(user=self.user, is_active=True).exists())

    def test_api_key_authenticates_requests(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_data['access']}")
        create_resp = self.client.post("/api/v1/auth/api-key/", {}, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        api_key = create_resp.data["key"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key}")
        me_resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(me_resp.data["email"], self.user.email)

    def test_revoke_api_key(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_data['access']}")
        create_resp = self.client.post("/api/v1/auth/api-key/", {}, format="json")
        api_key = create_resp.data["key"]
        revoke_resp = self.client.delete("/api/v1/auth/api-key/")
        self.assertEqual(revoke_resp.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key}")
        me_resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_api_key_returns_masked(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_data['access']}")
        self.client.post("/api/v1/auth/api-key/", {}, format="json")
        get_resp = self.client.get("/api/v1/auth/api-key/")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertIn("masked_key", get_resp.data)
        self.assertNotIn("key", get_resp.data)
        self.assertEqual(get_resp.data["masked_key"], "moio_****...****")

    def test_create_revokes_previous_key(self) -> None:
        login_data = _login(self.client, self.user.email, "pass1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_data['access']}")
        first = self.client.post("/api/v1/auth/api-key/", {}, format="json")
        key1 = first.data["key"]
        second = self.client.post("/api/v1/auth/api-key/", {}, format="json")
        key2 = second.data["key"]
        self.assertNotEqual(key1, key2)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key1}")
        me1 = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me1.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key2}")
        me2 = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me2.status_code, status.HTTP_200_OK)

    def test_api_key_requires_tenant(self) -> None:
        user_no_tenant = self._user_model.objects.create_user(
            email="notenant@example.com",
            username="no-tenant-user",
            password="pass1234",
            tenant=None,
            first_name="No",
            last_name="Tenant",
        )
        login_data = _login(self.client, user_no_tenant.email, "pass1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_data['access']}")
        response = self.client.post("/api/v1/auth/api-key/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tenant", response.data["error"].lower())
