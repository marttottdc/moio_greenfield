from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from chatbot.models.chatbot_session import ChatbotSession
from crm.models import Contact
from fluidcms import models
from portal.models import Tenant


class FluidcmsEndpointsTests(APITestCase):
    def setUp(self):
        # Ensure at least one topic exists if data migration did not run in tests
        if not models.Topic.objects.exists():
            self.topic = models.Topic.objects.create(
                slug="test-topic",
                title="Test Topic",
                short_description="A topic for testing",
                marketing_copy="Test marketing copy",
                benefits=["Benefit"],
                use_cases=["Use case"],
                pricing_tiers=[{"name": "Test", "price": "$0"}],
            )
        else:
            self.topic = models.Topic.objects.first()

        self.tenant = Tenant.objects.create(nombre="Test Tenant", domain="tenant.example.com")
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="landing-api-tester",
            email="tester@example.com",
            password="test-password",
            tenant=self.tenant,
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token.key}"}

    def _create_session(self):
        payload = {
            "referral": "google",
            "utm": {"source": "google", "medium": "cpc", "campaign": "spring"},
            "metadata": {"landing": "hero"},
        }
        response = self.client.post("/api/session", payload, format="json", **self.auth_headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response.data

    def test_session_initializes_contact_and_chatbot_session(self):
        session = self._create_session()
        visitor = models.VisitorSession.objects.get(id=session["id"])
        self.assertIsNotNone(visitor.contact)
        self.assertEqual(session["contact_id"], str(visitor.contact_id))
        self.assertEqual(visitor.contact.source, "webchat")
        self.assertTrue(
            ChatbotSession.objects.filter(session=str(visitor.id), contact=visitor.contact).exists()
        )

    def _create_content_fixture(self):
        page = models.ContentPage.objects.create(
            slug="home",
            name="Home",
            default_locale="en",
            metadata={"layout": "marketing"},
        )
        hero_section = models.ContentSection.objects.create(
            page=page,
            slug="hero",
            title="Hero",
            order=1,
            fallback_locale="en",
        )
        models.ContentBlock.objects.create(
            section=hero_section,
            key="hero",
            type=models.BLOCK_TYPE_HERO,
            locale="en",
            payload={
                "headline": "Automate customer journeys",
                "cta": {"label": "Get started", "href": "/start"},
            },
        )
        models.ContentBlock.objects.create(
            section=hero_section,
            key="hero",
            type=models.BLOCK_TYPE_HERO,
            locale="es",
            payload={
                "headline": "Automatiza tus recorridos",
                "cta": {"label": "Comenzar", "href": "/inicio"},
            },
        )

        features = models.ContentSection.objects.create(
            page=page,
            slug="features",
            title="Features",
            order=2,
            fallback_locale="en",
        )
        models.ContentBlock.objects.create(
            section=features,
            key="feature-list",
            type=models.BLOCK_TYPE_FEATURE_LIST,
            locale="en",
            fallback_locale="en",
            payload={
                "features": [
                    {"title": "Automation", "description": "Workflows and triggers"},
                    {"title": "Insights", "description": "Analytics dashboards"},
                ]
            },
        )
        models.ContentBlock.objects.create(
            section=features,
            key="cta",
            type=models.BLOCK_TYPE_CTA,
            locale="en",
            fallback_locale="en",
            payload={
                "title": "See the platform",
                "primaryCta": {"label": "Book a demo", "href": "/demo"},
            },
        )
        return page

    def test_session_requires_authentication(self):
        payload = {
            "referral": "google",
            "utm": {"source": "google"},
        }
        unauthenticated = self.client.post("/api/session", payload, format="json")
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        authenticated = self.client.post(
            "/api/session",
            payload,
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(authenticated.status_code, status.HTTP_201_CREATED)

    def test_topics_require_authentication(self):
        unauthenticated = self.client.get("/api/topics")
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        authenticated = self.client.get("/api/topics", **self.auth_headers)
        self.assertEqual(authenticated.status_code, status.HTTP_200_OK)

    def test_session_creation_and_update(self):
        session = self._create_session()
        session_id = session["id"]
        self.assertIsNotNone(session["contact_id"])

        update_payload = {
            "sessionId": session_id,
            "referral": "linkedin",
            "utm": {"medium": "social"},
        }
        response = self.client.post(
            "/api/session",
            update_payload,
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["referral_source"], "linkedin")
        self.assertEqual(response.data["utm_medium"], "social")
        self.assertEqual(response.data["contact_id"], session["contact_id"])

    def test_topic_catalog_and_detail(self):
        response = self.client.get("/api/topics", **self.auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

        detail = self.client.get(f"/api/topics/{self.topic.slug}", **self.auth_headers)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["slug"], self.topic.slug)

    def test_chat_flow_and_analytics(self):
        session = self._create_session()
        session_id = session["id"]

        visit_response = self.client.post(
            "/api/track/topic-visit",
            {"sessionId": session_id, "topic": self.topic.slug},
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(visit_response.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(user_id=session_id)
        interests = contact.traits.get("interests", [])
        self.assertIn(self.topic.slug, [entry.get("slug") for entry in interests])

        chat_payload = {
            "sessionId": session_id,
            "topic": self.topic.slug,
            "message": "Tell me more about pricing",
        }
        chat_response = self.client.post(
            "/api/agent/chat",
            chat_payload,
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(chat_response.status_code, status.HTTP_201_CREATED)
        self.assertIn("assistant_message", chat_response.data)
        self.assertGreaterEqual(len(chat_response.data.get("suggestions", [])), 1)
        message_index = chat_response.data.get("messageIndex")
        self.assertIsInstance(message_index, int)
        self.assertGreater(message_index, 0)
        self.assertEqual(
            models.ConversationMessage.objects.filter(session_id=session_id).count(),
            2,
        )

        like_response = self.client.post(
            "/api/likes",
            {"sessionId": session_id, "topic": self.topic.slug, "messageIndex": message_index},
            format="json",
            **self.auth_headers,
        )
        self.assertIn(like_response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(like_response.data["message"], models.ConversationMessage.objects.get(session_id=session_id, session_sequence=message_index).id)

        analytics = self.client.get(
            f"/api/session/{session_id}/analytics",
            **self.auth_headers,
        )
        self.assertEqual(analytics.status_code, status.HTTP_200_OK)
        self.assertEqual(analytics.data["session"]["id"], session_id)
        self.assertEqual(analytics.data["likes"], 1)
        self.assertGreaterEqual(analytics.data["engagement_score"], 1)

    def test_transports_and_meeting_schedule(self):
        session = self._create_session()
        session_id = session["id"]

        email_response = self.client.post(
            "/api/email/send",
            {"sessionId": session_id, "email": "person@example.com"},
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(email_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(models.EmailLog.objects.filter(id=email_response.data["id"]).exists())
        contact = Contact.objects.get(user_id=session_id)
        self.assertEqual(contact.email, "person@example.com")

        whatsapp_response = self.client.post(
            "/api/whatsapp/send",
            {"sessionId": session_id, "phone": "+15555555555"},
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(whatsapp_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(models.WhatsAppLog.objects.filter(id=whatsapp_response.data["id"]).exists())
        contact.refresh_from_db()
        self.assertEqual(contact.phone, "+15555555555")

        schedule_response = self.client.post(
            "/api/meeting/schedule",
            {
                "sessionId": session_id,
                "attendee": {"name": "Casey Customer", "email": "casey@example.com"},
                "provider": "google",
                "scheduledFor": (timezone.now() + timezone.timedelta(days=1)).isoformat(),
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(schedule_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(models.MeetingBooking.objects.filter(id=schedule_response.data["id"]).exists())
        contact.refresh_from_db()
        self.assertEqual(contact.fullname, "Casey Customer")
        self.assertEqual(contact.email, "casey@example.com")

    def test_session_contact_reuses_existing_contact_by_email(self):
        session = self._create_session()
        session_obj = models.VisitorSession.objects.get(id=session["id"])
        existing = Contact.objects.create(
            user_id="existing-email-contact",
            tenant=self.tenant,
            fullname="Returning Lead",
            email="person@example.com",
            source="import",
        )

        response = self.client.post(
            "/api/email/send",
            {"sessionId": session_obj.id, "email": existing.email},
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        session_obj.refresh_from_db()
        self.assertEqual(session_obj.contact_id, existing.user_id)
        chatbot_session = ChatbotSession.objects.get(session=str(session_obj.id))
        self.assertEqual(chatbot_session.contact_id, existing.user_id)

    def test_session_contact_reuses_existing_contact_by_phone(self):
        session = self._create_session()
        session_obj = models.VisitorSession.objects.get(id=session["id"])
        existing = Contact.objects.create(
            user_id="existing-phone-contact",
            tenant=self.tenant,
            fullname="WhatsApp Lead",
            phone="+15556667777",
            source="import",
        )

        response = self.client.post(
            "/api/whatsapp/send",
            {"sessionId": session_obj.id, "phone": "+1 (555) 666-7777"},
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        session_obj.refresh_from_db()
        self.assertEqual(session_obj.contact_id, existing.user_id)

    def test_content_page_locale_and_fallback(self):
        page = self._create_content_fixture()
        response_es = self.client.get(
            f"/api/content/pages/{page.slug}?locale=es",
            **self.auth_headers,
        )
        self.assertEqual(response_es.status_code, status.HTTP_200_OK)
        self.assertEqual(response_es.data["locale"]["requested"], "es")
        hero_section = next(section for section in response_es.data["sections"] if section["slug"] == "hero")
        hero_block = hero_section["blocks"][0]
        self.assertEqual(hero_block["locale"]["resolved"], "es")

        response_fr = self.client.get(
            f"/api/content/pages/{page.slug}?locale=fr",
            **self.auth_headers,
        )
        self.assertEqual(response_fr.status_code, status.HTTP_200_OK)
        self.assertTrue(response_fr.data["locale"]["fallbackApplied"])
        hero_section_fr = next(section for section in response_fr.data["sections"] if section["slug"] == "hero")
        hero_block_fr = hero_section_fr["blocks"][0]
        self.assertTrue(hero_block_fr["locale"]["fallbackApplied"])
        self.assertEqual(hero_block_fr["locale"]["resolved"], "en")

    def test_content_sitemap_endpoint(self):
        page = self._create_content_fixture()
        response = self.client.get("/api/content/sitemap", **self.auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data.get("pages", [])), 1)
        sitemap_entry = next(entry for entry in response.data["pages"] if entry["slug"] == page.slug)
        self.assertIn("es", sitemap_entry["locales"])
        hero_section = next(section for section in sitemap_entry["sections"] if section["slug"] == "hero")
        self.assertIn("hero", hero_section["blockKeys"])

    def test_conversation_messages_endpoints(self):
        session = self._create_session()
        session_id = session["id"]
        chat_payload = {
            "sessionId": session_id,
            "topic": self.topic.slug,
            "message": "Let's chat",
        }
        chat_response = self.client.post(
            "/api/agent/chat",
            chat_payload,
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(chat_response.status_code, status.HTTP_201_CREATED)

        list_response = self.client.get(
            f"/api/agent/conversations/{session_id}",
            **self.auth_headers,
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["total"], 2)
        self.assertEqual(len(list_response.data["results"]), 2)

        delete_response = self.client.delete(
            f"/api/agent/conversations/{session_id}",
            **self.auth_headers,
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(delete_response.data["deleted"], 2)
        self.assertEqual(
            models.ConversationMessage.objects.filter(session_id=session_id).count(),
            0,
        )

    def test_can_create_and_update_topics(self):
        payload = {
            "slug": "new-topic",
            "title": "New Topic",
            "short_description": "A fresh topic",
            "marketing_copy": "Brand new topic", 
            "benefits": ["Benefit"],
            "use_cases": ["Use"],
            "pricing_tiers": [{"name": "Free", "price": "$0"}],
        }

        create_response = self.client.post(
            "/api/topics", payload, format="json", **self.auth_headers
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        update_response = self.client.put(
            "/api/topics/new-topic",
            {**payload, "title": "Updated Topic"},
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["title"], "Updated Topic")
        self.assertTrue(models.Topic.objects.filter(slug="new-topic", title="Updated Topic").exists())

    def test_can_create_and_update_content_pages(self):
        payload = {
            "slug": "new-page",
            "name": "New Page",
            "description": "Landing page",
            "layout": "marketing",
            "defaultLocale": "en",
            "sections": [
                {
                    "slug": "hero",
                    "title": "Hero",
                    "order": 1,
                    "fallbackLocale": "en",
                    "blocks": [
                        {
                            "key": "hero",
                            "type": models.BLOCK_TYPE_HERO,
                            "locale": "en",
                            "payload": {
                                "headline": "Automate everything",
                                "cta": {"label": "Start", "href": "/start"},
                            },
                        }
                    ],
                },
                {
                    "slug": "features",
                    "title": "Features",
                    "order": 2,
                    "blocks": [
                        {
                            "key": "feature-list",
                            "type": models.BLOCK_TYPE_FEATURE_LIST,
                            "locale": "en",
                            "payload": {
                                "features": [
                                    {"title": "Automation", "description": "Do more"},
                                    {"title": "Insights", "description": "Know more"},
                                ]
                            },
                        }
                    ],
                },
            ],
        }

        create_response = self.client.post(
            "/api/content/pages", payload, format="json", **self.auth_headers
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["slug"], payload["slug"])
        self.assertEqual(len(create_response.data["sections"]), 2)

        update_payload = {
            **payload,
            "name": "Updated Page",
            "sections": [
                {
                    "slug": "hero",
                    "title": "Hero Updated",
                    "order": 1,
                    "fallbackLocale": "en",
                    "blocks": [
                        {
                            "key": "hero",
                            "type": models.BLOCK_TYPE_HERO,
                            "locale": "en",
                            "payload": {
                                "headline": "Automate faster",
                                "cta": {"label": "Begin", "href": "/begin"},
                            },
                        }
                    ],
                }
            ],
        }

        update_response = self.client.put(
            f"/api/content/pages/{payload['slug']}",
            update_payload,
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "Updated Page")
        self.assertEqual(len(update_response.data["sections"]), 1)
        self.assertEqual(update_response.data["sections"][0]["title"], "Hero Updated")
        self.assertFalse(
            models.ContentSection.objects.filter(page__slug=payload["slug"], slug="features").exists()
        )

    def test_block_payload_validation(self):
        page = models.ContentPage.objects.create(slug="validation", name="Validation", default_locale="en")
        section = models.ContentSection.objects.create(page=page, slug="hero", order=1)
        with self.assertRaises(DjangoValidationError):
            models.ContentBlock.objects.create(
                section=section,
                key="hero",
                type=models.BLOCK_TYPE_HERO,
                locale="en",
                payload={"headline": "Missing CTA"},
            )
