from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from central_hub.rbac import user_has_role, require_role, RequireHumanUser


class RbacHelperTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.factory = APIRequestFactory()
        self.manager_group, _ = Group.objects.get_or_create(name="manager")

    def test_user_has_role_respects_hierarchy(self):
        user = self.User.objects.create_user(email="u@example.com", username="u", password="x")
        self.assertFalse(user_has_role(user, "member"))

        user.groups.add(self.manager_group)
        self.assertTrue(user_has_role(user, "member"))
        self.assertTrue(user_has_role(user, "manager"))
        self.assertFalse(user_has_role(user, "tenant_admin"))

    def test_user_has_role_superuser_bypass(self):
        superuser = self.User.objects.create_superuser(email="s@example.com", username="s", password="x")
        self.assertTrue(user_has_role(superuser, "tenant_admin"))
        self.assertTrue(user_has_role(superuser, "platform_admin"))

    def test_require_role_decorator_enforces_permission(self):
        guarded_view = require_role("manager")(lambda self, request: Response({"ok": True}))

        # No role -> forbidden
        user = self.User.objects.create_user(email="n@example.com", username="n", password="x")
        request = self.factory.get("/")
        request.user = user
        resp = guarded_view(None, request)
        self.assertEqual(resp.status_code, 403)

        # With manager role -> allowed
        user.groups.add(self.manager_group)
        request = self.factory.get("/")
        request.user = user
        resp = guarded_view(None, request)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"ok": True})

    def test_require_human_user_blocks_service_tokens(self):
        perm = RequireHumanUser()

        # Authenticated human
        user = self.User.objects.create_user(email="h@example.com", username="h", password="x")
        request = self.factory.get("/")
        request.user = user
        request.auth = None
        self.assertTrue(perm.has_permission(request, None))

        # Service token (request.auth is dict)
        service_user = SimpleNamespace(is_authenticated=True)
        request = self.factory.get("/")
        request.user = service_user
        request.auth = {"scopes": ["service.read"]}
        self.assertFalse(perm.has_permission(request, None))

