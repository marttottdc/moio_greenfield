from __future__ import annotations

import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


TEST_MIDDLEWARE = list(settings.MIDDLEWARE)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
@unittest.skipIf(getattr(settings, "DJANGO_TENANTS_ENABLED", False), "CRM v2 tests run in non-tenant mode")
class CrmV2ApiTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="crm-v2-user",
            email="crm-v2@example.com",
            password="test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_WORKSPACE="main")

    def test_crm_v2_sales_and_support_flow(self) -> None:
        pipeline_res = self.client.post("/api/v1/crm/pipelines/create-default/", {}, format="json")
        self.assertEqual(pipeline_res.status_code, 201)
        pipeline_id = pipeline_res.data["id"]
        stage_id = pipeline_res.data["stages"][0]["id"]
        won_stage_id = next(row["id"] for row in pipeline_res.data["stages"] if row["is_closed_won"])

        account_res = self.client.post(
            "/api/v1/crm/accounts/",
            {
                "name": "Moio Labs",
                "industry": "Software",
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(account_res.status_code, 201)
        account_id = account_res.data["id"]

        contact_res = self.client.post(
            "/api/v1/crm/contacts/",
            {
                "first_name": "Ana",
                "last_name": "Perez",
                "email": "ana@example.com",
                "status": "lead",
            },
            format="json",
        )
        self.assertEqual(contact_res.status_code, 201)
        contact_id = contact_res.data["id"]

        link_res = self.client.post(
            "/api/v1/crm/account-links/",
            {
                "account": account_id,
                "contact": contact_id,
                "role": "Buyer",
                "is_primary": True,
            },
            format="json",
        )
        self.assertEqual(link_res.status_code, 201)

        deal_res = self.client.post(
            "/api/v1/crm/deals/",
            {
                "title": "Expansion 2026",
                "account": account_id,
                "contact": contact_id,
                "pipeline": pipeline_id,
                "stage": stage_id,
                "value": "15000.00",
                "currency": "USD",
                "priority": "high",
            },
            format="json",
        )
        self.assertEqual(deal_res.status_code, 201)
        deal_id = deal_res.data["id"]

        move_stage_res = self.client.post(
            f"/api/v1/crm/deals/{deal_id}/move-stage/",
            {"stage": won_stage_id, "comment": "Closed after procurement approval"},
            format="json",
        )
        self.assertEqual(move_stage_res.status_code, 200)
        self.assertEqual(move_stage_res.data["status"], "won")

        ticket_res = self.client.post(
            "/api/v1/crm/tickets/",
            {
                "subject": "Onboarding issue",
                "description": "Customer cannot access workspace",
                "account": account_id,
                "contact": contact_id,
                "priority": "high",
            },
            format="json",
        )
        self.assertEqual(ticket_res.status_code, 201)
        ticket_id = ticket_res.data["id"]

        ticket_comment_res = self.client.post(
            f"/api/v1/crm/tickets/{ticket_id}/comments/",
            {"body": "Assigned to onboarding pod"},
            format="json",
        )
        self.assertEqual(ticket_comment_res.status_code, 201)

        dashboard_res = self.client.get("/api/v1/crm/dashboard/summary/")
        self.assertEqual(dashboard_res.status_code, 200)
        self.assertEqual(dashboard_res.data["accounts"], 1)
        self.assertEqual(dashboard_res.data["contacts"], 1)
        self.assertEqual(dashboard_res.data["wonDeals"], 1)
        self.assertEqual(dashboard_res.data["openTickets"], 1)

    def test_crm_v2_capture_activity_and_knowledge_flow(self) -> None:
        activity_type_res = self.client.post(
            "/api/v1/crm/activity-types/",
            {
                "name": "Follow-up Task",
                "category": "task",
                "requires_contact": False,
                "requires_account": False,
            },
            format="json",
        )
        self.assertEqual(activity_type_res.status_code, 201)

        activity_res = self.client.post(
            "/api/v1/crm/activities/",
            {
                "kind": "task",
                "title": "Prepare kickoff",
                "status": "planned",
                "visibility": "internal",
                "type": activity_type_res.data["id"],
                "content": {"owner_note": "Need project brief"},
            },
            format="json",
        )
        self.assertEqual(activity_res.status_code, 201)

        capture_res = self.client.post(
            "/api/v1/crm/capture-entries/",
            {
                "anchor_type": "contact",
                "anchor_id": "external-contact-ref",
                "raw_text": "Call customer next week to confirm kickoff scope.",
            },
            format="json",
        )
        self.assertEqual(capture_res.status_code, 201)
        entry_id = capture_res.data["id"]

        classify_res = self.client.post(f"/api/v1/crm/capture-entries/{entry_id}/classify/", {}, format="json")
        self.assertEqual(classify_res.status_code, 200)
        self.assertEqual(classify_res.data["status"], "classified")

        apply_res = self.client.post(f"/api/v1/crm/capture-entries/{entry_id}/apply/", {}, format="json")
        self.assertEqual(apply_res.status_code, 200)
        self.assertEqual(apply_res.data["status"], "applied")
        self.assertIsNotNone(apply_res.data["applied_activity"])

        knowledge_res = self.client.post(
            "/api/v1/crm/knowledge-items/",
            {
                "title": "Implementation checklist",
                "summary": "Kickoff checklist for enterprise accounts",
                "body": "1. Create workspace\n2. Invite champion\n3. Schedule training",
                "kind": "playbook",
                "category": "onboarding",
            },
            format="json",
        )
        self.assertEqual(knowledge_res.status_code, 201)

        knowledge_list_res = self.client.get("/api/v1/crm/knowledge-items/?search=checklist")
        self.assertEqual(knowledge_list_res.status_code, 200)
        self.assertEqual(knowledge_list_res.data["count"], 1)

    def test_crm_v2_meta_catalog_exposes_new_resources(self) -> None:
        catalog_res = self.client.get("/api/v1/crm/meta/endpoints/")
        self.assertEqual(catalog_res.status_code, 200)
        self.assertEqual(catalog_res.data["module"], "crm")
        paths = {row["path"] for row in catalog_res.data["endpoints"]}
        self.assertIn("/api/v1/crm/accounts/", paths)
        self.assertIn("/api/v1/crm/capture-entries/", paths)
        self.assertIn("/api/v1/crm/knowledge-items/", paths)
