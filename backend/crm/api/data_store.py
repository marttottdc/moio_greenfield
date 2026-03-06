from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import timedelta, timezone as dt_timezone
from typing import Dict, List, Optional

from django.utils import timezone


def _iso(dt: timezone.datetime) -> str:
    """Return an ISO8601 string without microseconds."""

    return dt.astimezone(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DemoDataStore:
    """Small in-memory store that powers the public API mocks.

    The CI contract tests only need deterministic, well-structured payloads so we
    keep everything in memory. This avoids database setup while still exercising
    the serializers and view logic.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        last_week = now - timedelta(days=7)

        self.contacts: Dict[str, Dict] = {}
        base_contacts = [
            {
                "name": "LUIS ZAPATA",
                "email": "luis.zapata@example.com",
                "phone": "+59892637130",
                "company": "Tech Solutions SA",
                "type": "Customer",
                "tags": ["vip", "tech"],
                "custom_fields": {"source": "Website", "industry": "Technology"},
                "activity_summary": {
                    "total_deals": 3,
                    "total_tickets": 5,
                    "total_messages": 47,
                    "last_contact": _iso(yesterday),
                },
                "created_at": _iso(last_week),
                "updated_at": _iso(yesterday),
            },
            {
                "name": "MATÍAS CASTRO",
                "email": "matias.castro@example.com",
                "phone": "+59894790642",
                "company": "Castro Enterprises",
                "type": "Lead",
                "tags": ["new", "priority"],
                "custom_fields": {"source": "Referral", "industry": "Retail"},
                "activity_summary": {
                    "total_deals": 1,
                    "total_tickets": 0,
                    "total_messages": 8,
                    "last_contact": _iso(last_week),
                },
                "created_at": _iso(last_week),
                "updated_at": _iso(last_week),
            },
        ]

        for payload in base_contacts:
            contact_id = str(uuid.uuid4())
            self.contacts[contact_id] = {"id": contact_id, **deepcopy(payload)}

        self.deals: List[Dict] = [
            {
                "id": str(uuid.uuid4()),
                "name": "WhatsApp Onboarding - Tienda Inglesa",
                "stage": "qualification",
                "value": 12500,
                "currency": "USD",
                "owner": {"id": "owner-1", "name": "María García"},
                "contact": {"id": list(self.contacts.keys())[0], "name": "LUIS ZAPATA"},
                "probability": 0.55,
                "expected_close": _iso(now + timedelta(days=10)),
                "updated_at": _iso(yesterday),
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Seasonal Staffing - Punta",
                "stage": "proposal",
                "value": 4200,
                "currency": "USD",
                "owner": {"id": "owner-2", "name": "Joaquín Pérez"},
                "contact": {"id": list(self.contacts.keys())[1], "name": "MATÍAS CASTRO"},
                "probability": 0.32,
                "expected_close": _iso(now + timedelta(days=20)),
                "updated_at": _iso(now),
            },
        ]

        self.campaigns: List[Dict] = [
            {
                "id": str(uuid.uuid4()),
                "name": "Confirmación Punta Y Alrededores 1",
                "type": "Express Campaign",
                "description": "Envío de WhatsApp para confirmar selección",
                "status": "Active",
                "channel": "WhatsApp",
                "metrics": {
                    "sent": 1247,
                    "delivered": 1240,
                    "opened": 989,
                    "clicked": 234,
                    "conversion_rate": 18.8,
                },
                "target_audience": {
                    "total_contacts": 1500,
                    "filters": {"type": "Lead", "tags": ["punta", "confirmed"]},
                },
                "schedule": {"send_at": _iso(now + timedelta(days=2)), "timezone": "America/Montevideo"},
                "created_at": _iso(last_week),
                "updated_at": _iso(now),
            }
        ]

        self.templates: List[Dict] = [
            {
                "id": str(uuid.uuid4()),
                "name": "Confirmación Entrevista",
                "channel": "WhatsApp",
                "category": "reminder",
                "language": "es",
                "updated_at": _iso(yesterday),
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Seguimiento Lead",
                "channel": "Email",
                "category": "follow_up",
                "language": "es",
                "updated_at": _iso(last_week),
            },
        ]

        self.flows: List[Dict] = [
            {
                "id": str(uuid.uuid4()),
                "name": "Lead Nurturing Automation",
                "description": "Envía mensajes y crea deals para leads calientes",
                "status": "Active",
                "trigger": {"type": "contact_created", "conditions": {"contact_type": "Lead"}},
                "actions_count": 5,
                "executions": {
                    "total": 1247,
                    "successful": 1198,
                    "failed": 49,
                    "last_execution": _iso(yesterday),
                },
                "created_at": _iso(last_week - timedelta(days=14)),
                "updated_at": _iso(yesterday),
            }
        ]

        self.flow_runs: List[Dict] = [
            {
                "id": str(uuid.uuid4()),
                "flow_id": self.flows[0]["id"],
                "status": "success",
                "duration_ms": 2300,
                "triggered_by": {"type": "contact", "id": list(self.contacts.keys())[0]},
                "started_at": _iso(yesterday),
                "finished_at": _iso(yesterday + timedelta(seconds=2)),
            }
        ]

        self.chats: List[Dict] = [
            {
                "id": str(uuid.uuid4()),
                "contact": {
                    "id": list(self.contacts.keys())[0],
                    "name": "LUIS ZAPATA",
                    "phone": "+59892637130",
                    "avatar_url": None,
                },
                "channel": "WhatsApp",
                "last_message": {
                    "id": str(uuid.uuid4()),
                    "content": "Confirmado: asistencia a entrevista",
                    "sender": "contact",
                    "timestamp": _iso(yesterday),
                    "status": "delivered",
                },
                "unread_count": 1,
                "updated_at": _iso(yesterday),
                "tags": ["confirmation", "interview"],
            }
        ]

        self.channels: List[Dict] = [
            {
                "id": "whatsapp",
                "name": "WhatsApp Business",
                "status": "connected",
                "last_synced_at": _iso(now - timedelta(minutes=5)),
                "metadata": {"phone_number": "+59892637130"},
            },
            {
                "id": "email",
                "name": "SMTP",
                "status": "connected",
                "last_synced_at": _iso(now - timedelta(hours=2)),
                "metadata": {"inbox": "info@moio.ai"},
            },
        ]

        self.dashboard_summary: Dict = {
            "kpis": {
                "total_contacts": len(self.contacts),
                "active_campaigns": len(self.campaigns),
                "open_deals": len(self.deals),
                "automation_runs": len(self.flow_runs),
            },
            "pipeline": {
                "qualification": sum(1 for deal in self.deals if deal["stage"] == "qualification"),
                "proposal": sum(1 for deal in self.deals if deal["stage"] == "proposal"),
                "negotiation": 0,
                "won": 0,
            },
            "activities": [
                {
                    "type": "campaign_sent",
                    "title": self.campaigns[0]["name"],
                    "timestamp": _iso(now - timedelta(hours=6)),
                },
                {
                    "type": "flow_run",
                    "title": self.flows[0]["name"],
                    "timestamp": _iso(now - timedelta(hours=2)),
                },
            ],
            "generated_at": _iso(now),
        }

        self.navigation: Dict = {
            "primary": [
                {"label": "Dashboard", "path": "/dashboard", "icon": "layout", "badge": None},
                {"label": "Contacts", "path": "/contacts", "icon": "users", "badge": "hot"},
                {"label": "Deals", "path": "/deals", "icon": "kanban", "badge": None},
                {"label": "Campaigns", "path": "/campaigns", "icon": "megaphone", "badge": "new"},
            ],
            "secondary": [
                {"label": "Settings", "path": "/settings", "icon": "settings"},
                {"label": "Automation", "path": "/flows", "icon": "sparkles"},
            ],
            "feature_flags": {"automation_beta": True, "multi_tenant_admin": True},
            "updated_at": _iso(now),
        }

        self.topics: List[Dict] = [
            {
                "slug": "whatsapp-automation",
                "title": "Automatización de WhatsApp",
                "summary": "Secuencias automatizadas y confirmaciones",
                "trend": 12.4,
                "sentiment": "positive",
                "engagement_score": 86,
                "updated_at": _iso(now - timedelta(hours=1)),
            },
            {
                "slug": "seasonal-staffing",
                "title": "Zafra Punta 2025",
                "summary": "Campañas y confirmaciones para temporada",
                "trend": 8.1,
                "sentiment": "neutral",
                "engagement_score": 72,
                "updated_at": _iso(now - timedelta(hours=5)),
            },
        ]

    # ------------------------------------------------------------------
    # Contacts
    def list_contacts(self) -> List[Dict]:
        return list(self.contacts.values())

    def get_contact(self, contact_id: str) -> Optional[Dict]:
        contact = self.contacts.get(contact_id)
        return deepcopy(contact) if contact else None

    def create_contact(self, payload: Dict) -> Dict:
        contact_id = str(uuid.uuid4())
        now = _iso(timezone.now())
        record = {
            "id": contact_id,
            "name": payload.get("name", "Unnamed Contact"),
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "company": payload.get("company"),
            "type": payload.get("type", "Lead"),
            "tags": payload.get("tags", []),
            "custom_fields": payload.get("custom_fields", {}),
            "created_at": now,
            "updated_at": now,
            "activity_summary": {
                "total_deals": 0,
                "total_tickets": 0,
                "total_messages": 0,
                "last_contact": None,
            },
        }
        self.contacts[contact_id] = record
        return deepcopy(record)

    def update_contact(self, contact_id: str, payload: Dict) -> Optional[Dict]:
        contact = self.contacts.get(contact_id)
        if contact is None:
            return None
        for field in ["name", "email", "phone", "company", "type", "tags", "custom_fields"]:
            if field in payload and payload[field] is not None:
                contact[field] = payload[field]
        contact["updated_at"] = _iso(timezone.now())
        self.contacts[contact_id] = contact
        return deepcopy(contact)

    def delete_contact(self, contact_id: str) -> bool:
        return self.contacts.pop(contact_id, None) is not None

    # ------------------------------------------------------------------
    # Deals
    def list_deals(self) -> List[Dict]:
        return deepcopy(self.deals)

    def create_deal(self, payload: Dict) -> Dict:
        deal_id = str(uuid.uuid4())
        record = {
            "id": deal_id,
            "name": payload.get("name", "Untitled Deal"),
            "stage": payload.get("stage", "qualification"),
            "value": payload.get("value", 0),
            "currency": payload.get("currency", "USD"),
            "owner": payload.get("owner", {"id": "owner-self", "name": "Demo Owner"}),
            "contact": payload.get("contact"),
            "probability": payload.get("probability", 0.1),
            "expected_close": payload.get("expected_close", _iso(timezone.now() + timedelta(days=14))),
            "updated_at": _iso(timezone.now()),
        }
        self.deals.append(record)
        return deepcopy(record)

    # ------------------------------------------------------------------
    # Campaigns
    def list_campaigns(self) -> List[Dict]:
        return deepcopy(self.campaigns)

    def create_campaign(self, payload: Dict) -> Dict:
        campaign_id = str(uuid.uuid4())
        record = {
            "id": campaign_id,
            "name": payload.get("name", "Nueva campaña"),
            "type": payload.get("type", "Express Campaign"),
            "description": payload.get("description"),
            "status": "Draft",
            "channel": payload.get("channel", "WhatsApp"),
            "target_audience": payload.get("target_audience", {}),
            "schedule": payload.get("schedule", {}),
            "content": payload.get("content", {}),
            "estimated_reach": payload.get("target_audience", {}).get("estimated_contacts", 250),
            "created_at": _iso(timezone.now()),
        }
        self.campaigns.append(record)
        return deepcopy(record)

    def list_templates(self) -> List[Dict]:
        return deepcopy(self.templates)

    # ------------------------------------------------------------------
    # Flows & automation
    def list_flows(self) -> List[Dict]:
        return deepcopy(self.flows)

    def create_flow(self, payload: Dict) -> Dict:
        flow_id = str(uuid.uuid4())
        record = {
            "id": flow_id,
            "name": payload.get("name", "Nuevo flujo"),
            "description": payload.get("description"),
            "status": payload.get("status", "Testing"),
            "trigger": payload.get("trigger", {}),
            "actions": payload.get("actions", []),
            "created_at": _iso(timezone.now()),
            "message": "Flow created successfully",
        }
        self.flows.append(record)
        return deepcopy(record)

    def list_flow_runs(self) -> List[Dict]:
        return deepcopy(self.flow_runs)

    # ------------------------------------------------------------------
    # Communications
    def list_chats(self) -> List[Dict]:
        return deepcopy(self.chats)

    def list_channels(self) -> List[Dict]:
        return deepcopy(self.channels)

    # ------------------------------------------------------------------
    # Dashboard & platform
    def dashboard(self) -> Dict:
        return deepcopy(self.dashboard_summary)

    def navigation_payload(self) -> Dict:
        return deepcopy(self.navigation)

    def topics_payload(self) -> Dict:
        return {"topics": deepcopy(self.topics)}


demo_store = DemoDataStore()

