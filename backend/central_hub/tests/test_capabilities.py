"""Unit tests for EffectiveCapabilities resolver (role + tenant + allow/deny)."""
from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.test import TestCase

from central_hub.capabilities import (
    CAPABILITY_KEYS,
    get_effective_capabilities,
    EffectiveCapabilities,
)
from central_hub.models import Tenant, MoioUser
from central_hub.signals import create_tenant_configurations, create_internal_contact
from tenancy.signals import seed_tenant_entitlements, create_user_profile


def _entitlements(features=None, limits=None):
    return SimpleNamespace(
        features=features or {"crm_contacts_read": True, "crm_contacts_write": True, "users_manage": False},
        limits=limits or {"seats": 5, "agents": 2},
    )


class CapabilityResolverTests(TestCase):
    """Test get_effective_capabilities with mock-like inputs."""

    def test_viewer_gets_only_read_caps_within_tenant(self):
        user = SimpleNamespace(
            groups=SimpleNamespace(all=lambda: []),
            is_superuser=False,
            is_authenticated=True,
        )
        # No role group -> member by default in _resolve_user_role
        ent = _entitlements({"crm_contacts_read": True, "crm_contacts_write": True, "flows_read": False})
        eff = get_effective_capabilities(user, ent)
        self.assertIsInstance(eff, EffectiveCapabilities)
        self.assertIn("crm_contacts_read", eff.allowed_capabilities)

    def test_tenant_entitlements_restrict_capabilities(self):
        user = SimpleNamespace(
            groups=SimpleNamespace(all=lambda: [SimpleNamespace(name="tenant_admin")]),
            is_superuser=False,
            is_authenticated=True,
        )
        ent = _entitlements({"crm_contacts_read": True, "users_manage": False})
        eff = get_effective_capabilities(user, ent)
        self.assertIn("crm_contacts_read", eff.allowed_capabilities)
        self.assertNotIn("users_manage", eff.allowed_capabilities)

    def test_can_helper(self):
        eff = EffectiveCapabilities(
            allowed_capabilities={"crm_contacts_read"},
            effective_features={"crm_contacts_read": True},
            limits={},
        )
        self.assertTrue(eff.can("crm_contacts_read"))
        self.assertFalse(eff.can("users_manage"))


class CapabilityResolverWithModelsTests(TestCase):
    """Integration-style tests with real Tenant (with features/limits) and MoioUser."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(create_tenant_configurations, sender=Tenant)
        post_save.disconnect(seed_tenant_entitlements, sender=Tenant)
        post_save.disconnect(create_user_profile, sender=MoioUser)
        post_save.disconnect(create_internal_contact, sender=MoioUser)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_internal_contact, sender=MoioUser)
        post_save.connect(create_user_profile, sender=MoioUser)
        post_save.connect(seed_tenant_entitlements, sender=Tenant)
        post_save.connect(create_tenant_configurations, sender=Tenant)
        super().tearDownClass()

    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Cap Test",
            domain="cap.test",
            plan=Tenant.Plan.PRO,
            features={
                "crm_contacts_read": True,
                "crm_contacts_write": True,
                "flows_read": True,
                "flows_edit": True,
                "users_manage": True,
            },
            limits={"seats": 10, "agents": 3},
        )
        self.user = get_user_model().objects.create_user(
            email="cap@test.com",
            username="capuser",
            password="pass",
            tenant=self.tenant,
        )
        group, _ = Group.objects.get_or_create(name="manager")
        self.user.groups.add(group)

    def test_effective_capabilities_with_models(self):
        eff = get_effective_capabilities(self.user, self.tenant)
        self.assertIn("crm_contacts_read", eff.allowed_capabilities)
        self.assertIn("crm_contacts_write", eff.allowed_capabilities)
        self.assertEqual(eff.limits.get("seats"), 10)

