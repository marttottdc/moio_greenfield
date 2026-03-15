"""
Tests that KPI aggregation respects tenant RLS context.

- aggregate_kpis_for_tenant(rls_slug) must only count data for that tenant.
- run_full_sweep() must return the sum of per-tenant counts (loop with context, no RLS off).
"""
from __future__ import annotations

from django.test import TestCase

from tenancy.models import Tenant
from tenancy.tenant_support import tenant_rls_context

from central_hub.api.platform.kpi_aggregation import (
    aggregate_kpis_for_tenant,
    run_full_sweep,
)
from crm.models import Contact


class KpiAggregationTenantContextTests(TestCase):
    """Verify that KPI aggregation only sees data for the active tenant context."""

    def setUp(self):
        self.tenant_acme = Tenant.objects.create(
            nombre="Acme",
            domain="test.example.com",
            subdomain="acme",
            schema_name="acme",
            enabled=True,
        )
        self.tenant_orbit = Tenant.objects.create(
            nombre="Orbit",
            domain="test.example.com",
            subdomain="orbit",
            schema_name="orbit",
            enabled=True,
        )

    def test_aggregate_kpis_for_tenant_only_sees_that_tenant_contacts(self):
        """With tenant_rls_context(acme), only acme contacts are counted."""
        # Create 2 contacts for acme, 3 for orbit (each inside its context so RLS allows insert)
        with tenant_rls_context(self.tenant_acme.rls_slug):
            Contact.objects.create(
                tenant=self.tenant_acme,
                fullname="Acme One",
                email="a1@acme.test",
            )
            Contact.objects.create(
                tenant=self.tenant_acme,
                fullname="Acme Two",
                email="a2@acme.test",
            )
        with tenant_rls_context(self.tenant_orbit.rls_slug):
            Contact.objects.create(
                tenant=self.tenant_orbit,
                fullname="Orbit One",
                email="o1@orbit.test",
            )
            Contact.objects.create(
                tenant=self.tenant_orbit,
                fullname="Orbit Two",
                email="o2@orbit.test",
            )
            Contact.objects.create(
                tenant=self.tenant_orbit,
                fullname="Orbit Three",
                email="o3@orbit.test",
            )

        # Per-tenant aggregation must only see its own contacts
        with self.subTest("acme_context"):
            data_acme = aggregate_kpis_for_tenant(
                self.tenant_acme.rls_slug,
                start_dt=None,
                end_dt=None,
            )
            self.assertEqual(data_acme["contacts"], 2, "acme should see only 2 contacts")

        with self.subTest("orbit_context"):
            data_orbit = aggregate_kpis_for_tenant(
                self.tenant_orbit.rls_slug,
                start_dt=None,
                end_dt=None,
            )
            self.assertEqual(data_orbit["contacts"], 3, "orbit should see only 3 contacts")

    def test_run_full_sweep_sums_all_tenants(self):
        """run_full_sweep() loops per tenant with context; total = sum of per-tenant counts."""
        with tenant_rls_context(self.tenant_acme.rls_slug):
            Contact.objects.create(
                tenant=self.tenant_acme,
                fullname="Acme Only",
                email="acme@test",
            )
        with tenant_rls_context(self.tenant_orbit.rls_slug):
            Contact.objects.create(
                tenant=self.tenant_orbit,
                fullname="Orbit Only",
                email="orbit@test",
            )

        totals = run_full_sweep(tenant_slug=None, start_dt=None, end_dt=None)
        self.assertGreaterEqual(
            totals["contacts"],
            2,
            "run_full_sweep should sum contacts from all enabled tenants",
        )

    def test_run_full_sweep_single_tenant_only_sees_that_tenant(self):
        """run_full_sweep(tenant_slug=X) only aggregates tenant X."""
        with tenant_rls_context(self.tenant_acme.rls_slug):
            Contact.objects.create(
                tenant=self.tenant_acme,
                fullname="Acme Solo",
                email="acme-solo@test",
            )
        with tenant_rls_context(self.tenant_orbit.rls_slug):
            Contact.objects.create(
                tenant=self.tenant_orbit,
                fullname="Orbit Solo",
                email="orbit-solo@test",
            )

        totals_acme = run_full_sweep(
            tenant_slug=self.tenant_acme.subdomain,
            start_dt=None,
            end_dt=None,
        )
        totals_orbit = run_full_sweep(
            tenant_slug=self.tenant_orbit.subdomain,
            start_dt=None,
            end_dt=None,
        )
        self.assertEqual(totals_acme["contacts"], 1, "sweep(acme) should count only acme")
        self.assertEqual(totals_orbit["contacts"], 1, "sweep(orbit) should count only orbit")
