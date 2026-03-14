from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import RequestFactory, TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from central_hub.signals import create_internal_contact
from tenancy.authentication import TenantJWTAAuthentication, TenantTokenObtainPairSerializer
from tenancy.host_rewrite import HostRewriteFromJWTMiddleware
from tenancy.models import Tenant
from tenancy.resolution import attach_tenant_to_request, resolve_request_tenant, route_policy_for_request


class TenantResolutionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._user_model = get_user_model()
        post_save.disconnect(create_internal_contact, sender=cls._user_model)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_internal_contact, sender=cls._user_model)
        super().tearDownClass()

    def setUp(self):
        self.request_factory = RequestFactory()
        self.api_factory = APIRequestFactory()
        self.tenant = Tenant.objects.create(
            nombre="Acme",
            domain="example.com",
            subdomain="acme",
            schema_name="acme",
        )
        self.user = self._user_model.objects.create_user(
            email="tenant@example.com",
            username="tenant-user",
            password="pass1234",
            tenant=self.tenant,
        )
        self.other_tenant = Tenant.objects.create(
            nombre="Orbit",
            domain="example.com",
            subdomain="orbit",
            schema_name="orbit",
        )
        self.platform_user = self._user_model.objects.create_user(
            email="platform@example.com",
            username="platform-user",
            password="pass1234",
            tenant=None,
            is_staff=True,
        )

    def test_route_policy_classifies_boundary_paths(self):
        self.assertEqual(route_policy_for_request("/api/platform/bootstrap/"), "public")
        self.assertEqual(route_policy_for_request("/webhooks/demo/"), "external")
        self.assertEqual(route_policy_for_request("/api/v1/bootstrap/"), "tenant")
        self.assertEqual(route_policy_for_request("/api/v1/auth/me/"), "optional")

    def test_shopify_public_paths_are_external_with_or_without_trailing_slash(self):
        """RLS: Shopify embedded app and webhooks must be 'external' (no tenant) with or without trailing slash."""
        for path in (
            "/api/v1/integrations/shopify/embed/bootstrap",
            "/api/v1/integrations/shopify/embed/bootstrap/",
            "/api/v1/integrations/shopify/webhook/",
            "/api/v1/integrations/shopify/oauth/install/",
            "/api/v1/integrations/shopify/oauth/callback/",
            "/api/v1/integrations/shopify/chat-widget-config/",
            "/api/v1/integrations/shopify/app-proxy/foo",
        ):
            with self.subTest(path=path):
                self.assertEqual(route_policy_for_request(path), "external")

    def test_resolve_request_tenant_from_host(self):
        request = self.request_factory.get("/api/v1/bootstrap/", HTTP_HOST="acme.example.com")
        resolution = resolve_request_tenant(request)

        self.assertEqual(resolution.route_policy, "tenant")
        self.assertEqual(resolution.source, "host")
        self.assertEqual(getattr(resolution.tenant, "pk", None), self.tenant.pk)

    def test_resolve_request_tenant_prefers_jwt_over_host(self):
        refresh = TenantTokenObtainPairSerializer.get_token(self.user)
        request = self.api_factory.get(
            "/api/v1/bootstrap/",
            HTTP_HOST="orbit.example.com",
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}",
        )

        resolution = resolve_request_tenant(request)

        self.assertEqual(resolution.source, "jwt")
        self.assertEqual(getattr(resolution.tenant, "pk", None), self.tenant.pk)

    def test_jwt_auth_binds_tenant_for_tenant_route(self):
        refresh = TenantTokenObtainPairSerializer.get_token(self.user)
        request = self.api_factory.get(
            "/api/v1/desktop-agent/sessions/",
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}",
        )

        authenticated_user, _ = TenantJWTAAuthentication().authenticate(request)

        self.assertEqual(authenticated_user.pk, self.user.pk)
        self.assertEqual(getattr(getattr(request, "tenant", None), "pk", None), self.tenant.pk)
        self.assertEqual(getattr(request, "tenant_resolution_source", None), "jwt")

    def test_jwt_auth_allows_public_schema_route_without_tenant(self):
        refresh = TenantTokenObtainPairSerializer.get_token(self.platform_user)
        request = self.api_factory.get(
            "/api/platform/bootstrap/",
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}",
        )

        authenticated_user, _ = TenantJWTAAuthentication().authenticate(request)

        self.assertEqual(authenticated_user.pk, self.platform_user.pk)
        self.assertIsNone(getattr(request, "tenant", None))

    def test_jwt_auth_rejects_tenant_route_without_tenant(self):
        refresh = TenantTokenObtainPairSerializer.get_token(self.platform_user)
        request = self.api_factory.get(
            "/api/v1/bootstrap/",
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}",
        )

        with self.assertRaises(AuthenticationFailed):
            TenantJWTAAuthentication().authenticate(request)

    def test_attach_tenant_to_request_uses_explicit_user_without_touching_request_user(self):
        class ExplodingRequest:
            def __init__(self):
                self.tenant = None
                self.tenant_resolution_source = None
                self.tenant_route_policy = None

            @property
            def user(self):
                raise AssertionError("request.user should not be touched during tenant bind")

        request = ExplodingRequest()

        attach_tenant_to_request(
            request,
            self.tenant,
            user=self.user,
            source="jwt",
            route_policy="tenant",
        )

        self.assertEqual(getattr(request.tenant, "pk", None), self.tenant.pk)
        self.assertEqual(request.tenant_resolution_source, "jwt")
        self.assertEqual(request.tenant_route_policy, "tenant")
        self.assertEqual(getattr(self.user, "tenant_id", None), self.tenant.pk)

    def test_host_rewrite_from_jwt_uses_tenant_primary_domain(self):
        refresh = TenantTokenObtainPairSerializer.get_token(self.user)
        request = self.request_factory.get(
            "/api/v1/bootstrap/",
            HTTP_HOST="127.0.0.1:8093",
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}",
        )

        middleware = HostRewriteFromJWTMiddleware(lambda req: req)
        middleware(request)

        self.assertEqual(request.META["HTTP_HOST"], "acme.example.com")
