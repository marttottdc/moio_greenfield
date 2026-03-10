from django.test import TestCase

from central_hub.models import Tenant, TenantConfiguration


class TenantConfigurationTests(TestCase):
    def test_creating_multiple_tenants_generates_unique_default_whatsapp_names(self):
        first = Tenant.objects.create(nombre="Acme One", domain="one.test")
        second = Tenant.objects.create(nombre="Acme Two", domain="two.test")

        configs = list(
            TenantConfiguration.objects.filter(tenant__in=[first, second]).order_by("tenant__nombre")
        )

        self.assertEqual(len(configs), 2)
        whatsapp_names = [config.whatsapp_name for config in configs]
        self.assertTrue(all(whatsapp_names))
        self.assertEqual(len(whatsapp_names), len(set(whatsapp_names)))
