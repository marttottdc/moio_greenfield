"""
Shopify storefront chat WebSocket consumer.

No JWT: visitors are identified by anonymous_id (client-generated) or customer_id
(Shopify customer ID when logged in). Used for the chat widget in the storefront
app embed block. Agent channel: CHANNEL_SHOPIFY_WEBCHAT.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.db import IntegrityError
from django.utils import timezone
from agents import Runner, set_default_openai_key

from chatbot.models.agent_session import AgentSession, SessionThread
from chatbot.models.agent_configuration import AgentConfiguration, CHANNEL_SHOPIFY_WEBCHAT
from central_hub.tenant_config import get_tenant_config
from chatbot.agents.moio_agents_loader import build_agents_for_tenant

logger = logging.getLogger(__name__)


class ShopifyStorefrontChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket for storefront chat widget. No user auth; first message must be
    action "init" with shop_domain, anonymous_id, and optional customer_id.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialized = False
        self._session_group: Optional[str] = None
        self.shop_domain: Optional[str] = None
        self.tenant_id = None
        self.tenant = None
        self.session: Optional[AgentSession] = None
        self.agent_config: Optional[AgentConfiguration] = None
        self.tenant_config: Optional[Any] = None

    async def connect(self):
        await self.accept()
        logger.info("Shopify storefront chat connected (awaiting init)")

    async def disconnect(self, close_code):
        if getattr(self, "_session_group", None) and self.channel_layer:
            try:
                await self.channel_layer.group_discard(self._session_group, self.channel_name)
            except Exception:
                logger.warning("Shopify storefront chat group_discard failed: %s", self._session_group)
        if self.session:
            try:
                await self.close_session()
            except Exception:
                logger.exception(
                    "Failed closing Shopify storefront session shop=%s tenant=%s",
                    self.shop_domain,
                    self.tenant_id,
                )
        logger.info(
            "Shopify storefront chat disconnected shop=%s tenant=%s code=%s",
            self.shop_domain,
            self.tenant_id,
            close_code,
        )

    async def receive_json(self, content, **kwargs):
        try:
            action = content.get("action")
            data = content.get("data", {})

            if not self._initialized:
                if action != "init":
                    await self.send_json({
                        "event_type": "error",
                        "payload": {"message": "Send init first with shop_domain and anonymous_id", "code": "init_required"},
                    })
                    return
                logger.info("Shopify storefront chat init received shop_domain=%s", (data.get("shop_domain") or data.get("shop") or ""))
                await self.handle_init(data)
                return

            if action == "send_message":
                logger.info(
                    "Shopify storefront chat send_message shop=%s tenant=%s session_id=%s len=%s",
                    self.shop_domain,
                    self.tenant_id,
                    str(self.session.pk) if self.session else None,
                    len(str(data.get("content") or "")),
                )
                await self.handle_send_message(data)
            elif action == "get_history":
                logger.info(
                    "Shopify storefront chat get_history shop=%s tenant=%s session_id=%s",
                    self.shop_domain,
                    self.tenant_id,
                    str(self.session.pk) if self.session else None,
                )
                await self.handle_get_history(data)
            else:
                await self.send_json({
                    "event_type": "error",
                    "payload": {"message": f"Unknown action: {action}", "code": "unknown_action"},
                })
        except Exception as e:
            logger.exception("receive_json error")
            try:
                await self.send_json({
                    "event_type": "error",
                    "payload": {"message": "Something went wrong. Please try again.", "code": "server_error"},
                })
            except Exception:
                pass

    async def handle_init(self, data: Dict[str, Any]):
        shop_domain = (data.get("shop_domain") or data.get("shop") or "").strip()
        anonymous_id = (data.get("anonymous_id") or "").strip()
        requested_session_id = str(data.get("session_id") or "").strip()
        customer_id = data.get("customer_id")  # optional, Shopify customer id when logged in

        if not shop_domain or not anonymous_id:
            await self.send_json({
                "event_type": "error",
                "payload": {"message": "shop_domain and anonymous_id are required", "code": "invalid_init"},
            })
            await self.close(code=4000)
            return

        result = await self.resolve_tenant_and_contact(shop_domain, anonymous_id, customer_id)
        if result.get("error"):
            logger.info("Shopify storefront chat init failed shop=%s error=%s", shop_domain, result["error"])
            await self.send_json({
                "event_type": "error",
                "payload": {"message": result["error"], "code": "setup_failed"},
            })
            await self.close(code=4001)
            return

        self.shop_domain = shop_domain
        self.tenant_id = result["tenant_id"]
        self.tenant = result["tenant"]
        contact = result["contact"]

        agent_result = await self.get_agent_for_tenant(self.tenant_id)
        if agent_result.get("error"):
            logger.info("Shopify storefront chat init failed shop=%s tenant=%s error=%s", shop_domain, self.tenant_id, agent_result["error"])
            await self.send_json({
                "event_type": "error",
                "payload": {"message": agent_result["error"], "code": "agent_not_configured"},
            })
            await self.close(code=4002)
            return

        self.agent_config = agent_result["agent"]
        self.tenant_config = agent_result["tenant_config"]

        session_result = await self.get_or_create_session(contact, requested_session_id=requested_session_id)
        if session_result.get("error"):
            logger.info("Shopify storefront chat init failed shop=%s tenant=%s error=%s", shop_domain, self.tenant_id, session_result["error"])
            await self.send_json({
                "event_type": "error",
                "payload": {"message": session_result["error"], "code": "session_failed"},
            })
            await self.close(code=4003)
            return

        self.session = session_result["session"]
        self._initialized = True

        # session_id: widget must persist (e.g. localStorage) and send in next init to continue this session
        session_id_str = str(self.session.pk)
        logger.info(
            "Shopify storefront chat session_started shop=%s tenant=%s session_id=%s",
            self.shop_domain,
            self.tenant_id,
            session_id_str,
        )
        await self.send_json({
            "event_type": "session_started",
            "payload": {
                "conversation_id": session_id_str,
                "session_id": session_id_str,
                "agent_name": self.agent_config.name,
            },
        })
        self._session_group = f"shopify_chat_session_{session_id_str}"
        if getattr(self, "channel_layer", None):
            await self.channel_layer.group_add(self._session_group, self.channel_name)

    async def human_message(self, event):
        """Push human-mode message from communications center to the widget in real time."""
        await self.send_json({
            "event_type": "bot_message",
            "payload": {
                "role": "assistant",
                "content": event.get("content", ""),
                "author": event.get("author", ""),
                "timestamp": event.get("timestamp", ""),
            },
        })

    @database_sync_to_async
    def resolve_tenant_and_contact(self, shop_domain: str, anonymous_id: str, customer_id: Any) -> Dict[str, Any]:
        from tenancy.tenant_support import tenant_rls_context
        from central_hub.integrations.models import ShopifyShopLink, ShopifyShopLinkStatus

        link = ShopifyShopLink.objects.filter(
            shop_domain=shop_domain,
            status=ShopifyShopLinkStatus.LINKED,
        ).select_related("tenant").first()
        if not link or not link.tenant_id:
            return {"error": "Shop not linked"}

        tenant = link.tenant
        schema_name = getattr(tenant, "schema_name", None)
        from crm.models import Contact

        with tenant_rls_context(schema_name):
            contact = None
            if customer_id is not None and str(customer_id).strip():
                contact = Contact.objects.filter(
                    tenant=tenant,
                    external_ids__shopify=str(customer_id),
                ).first()
            if contact is None:
                contact = Contact.objects.filter(
                    tenant=tenant,
                    external_ids__shopify_webchat_anonymous=anonymous_id,
                ).first()
            if contact is None:
                contact = Contact.objects.create(
                    tenant=tenant,
                    fullname="Storefront visitor",
                    email="",
                    phone="",
                    source="shopify_webchat",
                    external_ids={
                        "shopify_webchat_anonymous": anonymous_id,
                        **({"shopify": str(customer_id)} if customer_id is not None and str(customer_id).strip() else {}),
                    },
                )
        return {"tenant_id": tenant.pk, "tenant": tenant, "contact": contact}

    @database_sync_to_async
    def get_agent_for_tenant(self, tenant_id) -> Dict[str, Any]:
        from tenancy.tenant_support import tenant_rls_context
        from tenancy.models import Tenant

        try:
            tenant = Tenant.objects.filter(pk=tenant_id).first()
            if not tenant:
                return {"error": "Tenant not found"}
            schema_name = getattr(tenant, "schema_name", None)
            with tenant_rls_context(schema_name):
                tenant_config = get_tenant_config(tenant)
                agent = AgentConfiguration.objects.filter(
                    tenant_id=tenant_id,
                    channel=CHANNEL_SHOPIFY_WEBCHAT,
                    enabled=True,
                ).order_by("-default").first()
                if not agent:
                    agent = AgentConfiguration.objects.filter(
                        tenant_id=tenant_id,
                        default=True,
                        enabled=True,
                    ).first()
                if not agent:
                    return {"error": "No agent configured for Shopify webchat. Set an agent with channel Shopify Webchat or a default agent."}
                return {"agent": agent, "tenant_config": tenant_config}
        except Exception as e:
            logger.exception("get_agent_for_tenant failed")
            return {"error": str(e)}

    @database_sync_to_async
    def get_or_create_session(self, contact, requested_session_id: str = "") -> Dict[str, Any]:
        from tenancy.tenant_support import tenant_rls_context

        try:
            schema_name = getattr(self.tenant, "schema_name", None) if self.tenant else None
            with tenant_rls_context(schema_name):
                if requested_session_id:
                    session = AgentSession.objects.filter(
                        pk=requested_session_id,
                        tenant_id=self.tenant_id,
                        contact=contact,
                        channel=CHANNEL_SHOPIFY_WEBCHAT,
                    ).first()
                    if session:
                        update_fields = []
                        if not session.active:
                            session.active = True
                            update_fields.append("active")
                        if session.end is not None:
                            session.end = None
                            update_fields.append("end")
                        session.last_interaction = timezone.now()
                        update_fields.append("last_interaction")
                        if update_fields:
                            session.save(update_fields=update_fields)
                        return {"session": session}

                session = AgentSession.objects.filter(
                    tenant_id=self.tenant_id,
                    contact=contact,
                    channel=CHANNEL_SHOPIFY_WEBCHAT,
                    active=True,
                ).order_by("-last_interaction").first()
                if session:
                    return {"session": session}

                session = AgentSession.objects.create(
                    tenant_id=self.tenant_id,
                    contact=contact,
                    channel=CHANNEL_SHOPIFY_WEBCHAT,
                    start=timezone.now(),
                    last_interaction=timezone.now(),
                    current_agent=self.agent_config.name if self.agent_config else "",
                    started_by="user",
                    agent_id=self.agent_config.id if self.agent_config else None,
                )
                try:
                    SessionThread.objects.create(
                        session=session,
                        role="system",
                        content=f"Shopify storefront chat session started. Shop: {self.shop_domain}",
                        author="moio",
                    )
                except IntegrityError as e:
                    logger.warning("get_or_create_session: could not create initial SessionThread: %s", e)
                return {"session": session}
        except Exception as e:
            logger.exception("get_or_create_session failed")
            return {"error": str(e)}

    async def handle_send_message(self, data: Dict[str, Any]):
        content = (data.get("content") or "").strip()
        if not content:
            await self.send_json({
                "event_type": "error",
                "payload": {"message": "Message content is required", "code": "empty_message"},
            })
            return

        if not self.session or not self.agent_config or not self.tenant_config:
            await self.send_json({
                "event_type": "error",
                "payload": {"message": "Session not initialized", "code": "no_session"},
            })
            return

        await self.send_json({
            "event_type": "message_received",
            "payload": {
                "role": "user",
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            },
        })

        await self.add_utterance(content, "user")

        await self.send_json({
            "event_type": "typing",
            "payload": {"status": "typing"},
        })

        try:
            response = await self.process_with_agent(content)
            if response:
                text_content, rich_content = self._extract_response_payload(response)
                await self.add_utterance(text_content, "assistant", author=self.agent_config.name)
                logger.info(
                    "Shopify storefront chat bot_message sent shop=%s tenant=%s session_id=%s",
                    self.shop_domain,
                    self.tenant_id,
                    str(self.session.pk) if self.session else None,
                )
                await self.send_json({
                    "event_type": "bot_message",
                    "payload": {
                        "role": "assistant",
                        "content": text_content,
                        "rich_content": rich_content,
                        "agent_name": self.agent_config.name,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                })
            else:
                await self.send_json({
                    "event_type": "error",
                    "payload": {"message": "Failed to get response", "code": "agent_error"},
                })
        except Exception as e:
            logger.exception("process_with_agent failed")
            await self.send_json({
                "event_type": "typing",
                "payload": {"status": "stopped"},
            })
            await self.send_json({
                "event_type": "error",
                "payload": {"message": str(e), "code": "agent_error"},
            })

    async def handle_get_history(self, data: Dict[str, Any]):
        if not self.session:
            logger.info("Shopify storefront chat history sent shop=%s count=0 (no session)", self.shop_domain)
            await self.send_json({"event_type": "history", "payload": {"messages": []}})
            return
        history = await self.get_session_history(str(self.session.pk))
        logger.info(
            "Shopify storefront chat history sent shop=%s tenant=%s session_id=%s count=%s",
            self.shop_domain,
            self.tenant_id,
            str(self.session.pk),
            len(history),
        )
        await self.send_json({"event_type": "history", "payload": {"messages": history}})

    @database_sync_to_async
    def add_utterance(self, content: str, role: str, author: str = ""):
        from tenancy.tenant_support import tenant_rls_context

        if not self.session:
            return
        if not author:
            author = role
        schema_name = getattr(self.tenant, "schema_name", None) if self.tenant else None
        with tenant_rls_context(schema_name):
            try:
                latest = SessionThread.objects.filter(session=self.session).latest("created")
                if latest.role == "user" and role == "user":
                    latest.content = f"{latest.content} {content}"
                    latest.stitches = getattr(latest, "stitches", 0) + 1
                    latest.save()
                    return
            except SessionThread.DoesNotExist:
                pass
            SessionThread.objects.create(
                session=self.session,
                role=role,
                content=content,
                author=author,
            )
            self.session.last_interaction = timezone.now()
            self.session.save(update_fields=["last_interaction"])

    @database_sync_to_async
    def get_session_history(self, session_id: str) -> list:
        from tenancy.tenant_support import tenant_rls_context

        try:
            schema_name = getattr(self.tenant, "schema_name", None) if self.tenant else None
            with tenant_rls_context(schema_name):
                messages = SessionThread.objects.filter(
                    session_id=session_id,
                ).exclude(role="system").order_by("created")
                return [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "author": getattr(msg, "author", msg.role),
                        "timestamp": msg.created.isoformat() if hasattr(msg, "created") and msg.created else None,
                    }
                    for msg in messages
                ]
        except Exception as e:
            logger.warning("get_session_history failed: %s", e)
            return []

    def _normalize_role_for_openai(self, role: Optional[str]) -> str:
        """OpenAI API expects 'assistant', 'user', 'system' (lowercase). SessionThread may store 'ASSISTANT'."""
        r = (role or "user").strip().lower()
        if r in ("assistant", "user", "system"):
            return r
        if r == "developer":
            return "developer"
        return "user"

    @database_sync_to_async
    def get_session_context(self) -> Optional[list]:
        from tenancy.tenant_support import tenant_rls_context

        if not self.session:
            return None
        schema_name = getattr(self.tenant, "schema_name", None) if self.tenant else None
        with tenant_rls_context(schema_name):
            messages = SessionThread.objects.filter(
                session=self.session,
            ).exclude(role="system").order_by("created")
            if not messages.exists():
                return None
            return [
                {"role": self._normalize_role_for_openai(msg.role), "content": msg.content}
                for msg in messages
            ]

    async def process_with_agent(self, user_message: str) -> Optional[Any]:
        if not self.agent_config or not self.tenant_config or not self.session:
            return None
        schema_name = getattr(self.tenant, "schema_name", None) if self.tenant else None
        session_context = await self.get_session_context()

        def run_agent():
            from tenancy.tenant_support import tenant_rls_context

            with tenant_rls_context(schema_name):
                openai_key = getattr(self.tenant_config, "openai_api_key", None) or ""
                set_default_openai_key(openai_key)
                agents_map = build_agents_for_tenant(self.session.tenant)
                agent = agents_map.get(self.agent_config.name) if agents_map else None
                if not agent:
                    logger.error("Agent %s not found for tenant %s", self.agent_config.name, self.session.tenant)
                    return None
                context = {
                    "session": self.session,
                    "contact": self.session.contact,
                    "config": self.tenant_config,
                }
                agent_input = user_message
                if session_context:
                    agent_input = session_context + [{"role": "user", "content": user_message}]
                result = Runner.run_sync(agent, input=agent_input, context=context)
                return result.final_output

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, run_agent)
        except Exception as e:
            logger.exception("process_with_agent failed")
            return None

    def _extract_response_payload(self, response: Any) -> tuple[str, Optional[dict]]:
        """Build a safe response payload with text fallback plus optional rich_content."""
        if response is None:
            return "", None

        if isinstance(response, dict):
            rich = self._normalize_rich_content(response.get("rich_content") or response.get("rich"))
            text = str(response.get("text") or response.get("message") or "").strip()
            # If there is no dedicated rich field, treat the whole object as a rich payload.
            if rich is None:
                rich = self._normalize_rich_content(response)
            if not text and rich:
                text = "Rich content"
            return text, rich

        if isinstance(response, str):
            raw = response.strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                except (TypeError, ValueError):
                    parsed = None
                if isinstance(parsed, dict):
                    rich = self._normalize_rich_content(parsed.get("rich_content") or parsed.get("rich"))
                    text = str(parsed.get("text") or parsed.get("message") or "").strip()
                    if rich is None:
                        rich = self._normalize_rich_content(parsed)
                    if rich:
                        if not text:
                            text = "Rich content"
                        return text, rich
            return raw, None

        return str(response), None

    def _normalize_rich_content(self, payload: Any) -> Optional[dict]:
        """Normalize known rich content shapes into {'items': [...]}."""
        if not isinstance(payload, dict):
            return None

        items = payload.get("items")
        if not isinstance(items, list):
            item_type = str(payload.get("type") or "").strip().lower()
            if item_type:
                items = [payload]
            else:
                return None

        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "image":
                url = str(item.get("url") or item.get("src") or "").strip()
                if not url:
                    continue
                normalized_items.append({
                    "type": "image",
                    "url": url,
                    "alt": str(item.get("alt") or "").strip(),
                    "link_url": str(item.get("link_url") or item.get("href") or "").strip(),
                })
            elif item_type == "link":
                url = str(item.get("url") or item.get("href") or "").strip()
                if not url:
                    continue
                normalized_items.append({
                    "type": "link",
                    "url": url,
                    "text": str(item.get("text") or item.get("label") or url).strip(),
                })
            elif item_type in {"button", "cta"}:
                url = str(item.get("url") or item.get("href") or "").strip()
                if not url:
                    continue
                normalized_items.append({
                    "type": "button",
                    "url": url,
                    "text": str(item.get("text") or item.get("label") or "Open").strip(),
                })

        if not normalized_items:
            return None
        return {"items": normalized_items}

    @database_sync_to_async
    def close_session(self):
        from tenancy.tenant_support import tenant_rls_context

        if not self.session:
            return
        schema_name = getattr(self.tenant, "schema_name", None) if self.tenant else None
        with tenant_rls_context(schema_name):
            self.session.active = False
            self.session.end = timezone.now()
            self.session.save(update_fields=["active", "end"])
