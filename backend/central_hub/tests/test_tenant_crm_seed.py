from django.test import TestCase

from crm.models import ContactType, ContactTypeChoices
from tenancy.models import Tenant


class TenantCrmSeedTests(TestCase):
    def test_new_tenant_seeds_default_contact_types(self):
        tenant = Tenant.objects.create(
            nombre="Seeded Tenant",
            domain="seeded.test",
            subdomain="seeded",
        )

        names = set(ContactType.objects.filter(tenant=tenant).values_list("name", flat=True))

        self.assertEqual(
            names,
            {
                ContactTypeChoices.LEAD,
                ContactTypeChoices.RECURRENT,
                ContactTypeChoices.EXPERT,
                ContactTypeChoices.CUSTOMER,
                ContactTypeChoices.VIP,
                ContactTypeChoices.ADMIN,
                ContactTypeChoices.INTERNAL,
                ContactTypeChoices.USER,
            },
        )
        self.assertEqual(
            ContactType.objects.filter(tenant=tenant, is_default=True).values_list("name", flat=True).get(),
            ContactTypeChoices.LEAD,
        )
