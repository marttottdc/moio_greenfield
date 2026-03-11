import asyncio
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from channels.db import database_sync_to_async
from django.utils import timezone
from agents import Runner, set_default_openai_key

from websockets_app.consumers.base import TenantAwareConsumer
from chatbot.models.chatbot_session import ChatbotSession, ChatbotMemory
from chatbot.models.agent_configuration import AgentConfiguration, CHANNEL_DESKTOP
from central_hub.models import MoioUser
from central_hub.tenant_config import get_tenant_config_by_id
from chatbot.agents.moio_agents_loader import build_agents_for_tenant

logger = logging.getLogger(__name__)


class DesktopCrmAgentConsumer(TenantAwareConsumer):
    channel_prefix = "crm_agent"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: Optional[ChatbotSession] = None
        self.agent_config: Optional[AgentConfiguration] = None
        self.tenant_config: Optional[Any] = None

    async def setup_groups(self):
        if self.user and self.tenant_id:
            group_name = f"crm_agent_{self.tenant_id}_{self.user.id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups.append(group_name)

    async def on_connect(self):
        agent_result = await self.get_user_agent()
        if agent_result.get("error"):
            await self.send_json({
                "event_type": "error",
                "payload": {"message": agent_result["error"], "code": "agent_not_configured"}
            })
            await self.close(code=4002)
            return

        self.agent_config = agent_result["agent"]
        self.tenant_config = agent_result["tenant_config"]

        session_result = await self.get_or_create_session()
        self.session = session_result["session"]

        await self.send_json({
            "event_type": "connected",
            "payload": {
                "channel": "crm_agent",
                "tenant_id": str(self.tenant_id),
                "agent_name": self.agent_config.name,
                "agent_id": str(self.agent_config.id),
                "session_id": str(self.session.session) if self.session else None
            }
        })

    async def on_message(self, action: str, data: Dict[str, Any]):
        if action == "send_message":
            await self.handle_send_message(data)
        elif action == "get_history":
            await self.handle_get_history(data)
        elif action == "close_session":
            await self.handle_close_session()
        elif action == "new_session":
            await self.handle_new_session()
        elif action == "resume_session":
            await self.handle_resume_session(data)
        else:
            await self.send_error(f"Unknown action: {action}")

    async def handle_send_message(self, data: Dict[str, Any]):
        content = data.get("content", "").strip()
        if not content:
            await self.send_error("Message content is required")
            return

        if not self.session or not self.agent_config or not self.tenant_config:
            await self.send_error("Session not initialized")
            return

        await self.send_json({
            "event_type": "message_received",
            "payload": {
                "role": "user",
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

        await self.add_utterance(content, "user")

        await self.send_json({
            "event_type": "agent_typing",
            "payload": {"status": "typing"}
        })

        try:
            response = await self.process_with_agent(content)
            if response:
                await self.add_utterance(response, "assistant", author=self.agent_config.name)
                await self.send_json({
                    "event_type": "message",
                    "payload": {
                        "role": "assistant",
                        "content": response,
                        "agent_name": self.agent_config.name,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                })
            else:
                await self.send_error("Failed to get agent response")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send_json({
                "event_type": "agent_typing",
                "payload": {"status": "stopped"}
            })
            await self.send_error(f"Error processing message: {str(e)}")

    async def handle_get_history(self, data: Dict[str, Any]):
        session_id = data.get("session_id")
        if session_id:
            history = await self.get_session_history(session_id)
        elif self.session:
            history = await self.get_session_history(str(self.session.session))
        else:
            history = []

        await self.send_json({
            "event_type": "history",
            "payload": {"messages": history}
        })

    async def handle_close_session(self):
        if self.session:
            await self.close_current_session()
            await self.send_json({
                "event_type": "session_closed",
                "payload": {"session_id": str(self.session.session)}
            })
            self.session = None

    async def handle_new_session(self):
        if self.session:
            await self.close_current_session()

        session_result = await self.get_or_create_session(force_new=True)
        self.session = session_result["session"]

        await self.send_json({
            "event_type": "session_created",
            "payload": {
                "session_id": str(self.session.session) if self.session else None,
                "agent_name": self.agent_config.name if self.agent_config else None
            }
        })

    async def handle_resume_session(self, data: Dict[str, Any]):
        session_id = data.get("session_id")
        if not session_id:
            await self.send_error("session_id is required")
            return

        session_result = await self.load_session(session_id)
        if session_result.get("error"):
            await self.send_error(session_result["error"])
            return

        self.session = session_result["session"]
        await self.send_json({
            "event_type": "session_resumed",
            "payload": {
                "session_id": str(self.session.session),
                "agent_name": self.agent_config.name if self.agent_config else None,
                "active": self.session.active
            }
        })

    @database_sync_to_async
    def get_user_agent(self) -> Dict[str, Any]:
        try:
            user = MoioUser.objects.get(pk=self.user.pk)
            preferences = user.preferences or {}
            agent_id = preferences.get("crm_desktop_agent_id")

            tenant_config = get_tenant_config_by_id(self.tenant_id)

            if agent_id:
                try:
                    agent = AgentConfiguration.objects.get(
                        id=agent_id,
                        tenant_id=self.tenant_id,
                        enabled=True
                    )
                    return {"agent": agent, "tenant_config": tenant_config}
                except AgentConfiguration.DoesNotExist:
                    pass

            try:
                agent = AgentConfiguration.objects.get(
                    tenant_id=self.tenant_id,
                    default=True,
                    enabled=True
                )
                return {"agent": agent, "tenant_config": tenant_config}
            except AgentConfiguration.DoesNotExist:
                return {"error": "No agent configured. Please configure a CRM desktop agent in your preferences or set a default agent."}

        except Exception as e:
            from django.core.exceptions import ObjectDoesNotExist
            if isinstance(e, ObjectDoesNotExist):
                return {"error": "Tenant configuration not found"}
            raise
        except Exception as e:
            logger.error(f"Error getting user agent: {e}")
            return {"error": str(e)}

    @database_sync_to_async
    def get_or_create_session(self, force_new: bool = False) -> Dict[str, Any]:
        from crm.models import Contact

        try:
            if not self.user or not self.tenant_id:
                return {"error": "Authentication required"}

            user_id = self.user.pk
            user_email = self.user.email

            if not user_email:
                return {"error": "User email is required"}

            user_contact = Contact.objects.filter(
                tenant_id=self.tenant_id,
                email=user_email
            ).first()

            if not user_contact:
                user_contact = Contact.objects.create(
                    tenant_id=self.tenant_id,
                    fullname=f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username,
                    email=user_email,
                    phone=getattr(self.user, 'phone', '') or '',
                )

            self._user_contact_id = user_contact.pk

            if not force_new:
                try:
                    session = ChatbotSession.objects.get(
                        tenant_id=self.tenant_id,
                        contact=user_contact,
                        channel=CHANNEL_DESKTOP,
                        active=True
                    )
                    return {"session": session}
                except ChatbotSession.DoesNotExist:
                    pass
                except ChatbotSession.MultipleObjectsReturned:
                    session = ChatbotSession.objects.filter(
                        tenant_id=self.tenant_id,
                        contact=user_contact,
                        channel=CHANNEL_DESKTOP,
                        active=True
                    ).latest("last_interaction")
                    return {"session": session}

            session = ChatbotSession.objects.create(
                tenant_id=self.tenant_id,
                contact=user_contact,
                channel=CHANNEL_DESKTOP,
                start=timezone.now(),
                last_interaction=timezone.now(),
                current_agent=self.agent_config.name if self.agent_config else "",
                started_by="user",
                agent_id=self.agent_config.id if self.agent_config else None
            )

            system_message = f"CRM Desktop Agent session started. User: {self.user.email}, Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}"
            ChatbotMemory.objects.create(
                session=session,
                role="system",
                content=system_message,
                author="moio"
            )

            return {"session": session}

        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return {"error": str(e)}

    @database_sync_to_async
    def add_utterance(self, content: str, role: str, author: str = ""):
        if not self.session:
            return

        if not author:
            author = role

        try:
            latest = ChatbotMemory.objects.filter(session=self.session).latest("created")
            if latest.role == "user" and role == "user":
                latest.content = f"{latest.content} {content}"
                latest.stitches += 1
                latest.save()
                return
        except ChatbotMemory.DoesNotExist:
            pass

        ChatbotMemory.objects.create(
            session=self.session,
            role=role,
            content=content,
            author=author
        )

        self.session.last_interaction = timezone.now()
        self.session.save(update_fields=["last_interaction"])

    @database_sync_to_async
    def get_session_history(self, session_id: str) -> list:
        try:
            messages = ChatbotMemory.objects.filter(
                session_id=session_id
            ).exclude(role="system").order_by("created")

            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "author": msg.author,
                    "timestamp": msg.created.isoformat()
                }
                for msg in messages
            ]
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return []

    @database_sync_to_async
    def load_session(self, session_id: str) -> Dict[str, Any]:
        from crm.models import Contact

        if not self.user or not self.tenant_id:
            return {"error": "Authentication required"}

        user_contact = Contact.objects.filter(
            tenant_id=self.tenant_id,
            email=self.user.email
        ).first()

        if not user_contact:
            return {"error": "User contact not found"}

        try:
            session = ChatbotSession.objects.get(
                session=session_id,
                tenant_id=self.tenant_id,
                contact=user_contact,
                channel=CHANNEL_DESKTOP
            )
            return {"session": session}
        except ChatbotSession.DoesNotExist:
            return {"error": "Session not found"}
        except Exception as e:
            logger.error(f"Error loading session: {e}")
            return {"error": str(e)}

    @database_sync_to_async
    def close_current_session(self):
        if self.session:
            self.session.active = False
            self.session.end = timezone.now()
            self.session.save(update_fields=["active", "end"])

    @database_sync_to_async
    def get_full_transcript(self) -> list:
        if not self.session:
            return []

        messages = []
        for msg in ChatbotMemory.objects.filter(session=self.session).order_by("created"):
            messages.append({
                "role": msg.role,
                "content": msg.content,
                "created": msg.created.strftime("%Y-%m-%d %H:%M:%S")
            })
        return messages

    @database_sync_to_async
    def get_session_context(self) -> Optional[list]:
        if not self.session:
            return None

        messages = ChatbotMemory.objects.filter(
            session=self.session
        ).exclude(role="system").order_by("created")

        if not messages.exists():
            return None

        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

    async def process_with_agent(self, user_message: str) -> Optional[str]:
        if not self.agent_config or not self.tenant_config or not self.session:
            return None

        try:
            session_context = await self.get_session_context()
            openai_key = self.tenant_config.openai_api_key

            def run_agent():
                set_default_openai_key(openai_key)

                agents_map = build_agents_for_tenant(self.session.tenant)
                agent = agents_map.get(self.agent_config.name)
                
                if not agent:
                    logger.error(f"Agent {self.agent_config.name} not found in tenant {self.session.tenant}")
                    return None

                context = {
                    "session": self.session,
                    "contact": self.session.contact,
                    "config": self.tenant_config,
                }

                if session_context is None:
                    agent_input = user_message
                else:
                    agent_input = session_context + [{"role": "user", "content": user_message}]

                result = Runner.run_sync(
                    agent,
                    input=agent_input,
                    context=context
                )
                return result.final_output

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, run_agent)
            return response

        except Exception as e:
            logger.error(f"Error running agent: {e}")
            return None
