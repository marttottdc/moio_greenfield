import asyncio
import json

from django.utils import timezone

import chatbot.events
from chatbot.agents.moio_agents_loader import build_agents_for_tenant
from chatbot.models.chatbot_session import ChatbotMemory

from crm.models import Contact, ContactType
from chatbot.models.agent_configuration import AgentConfiguration
from chatbot.lib.types import ConversationAnalysisModel, ConversationSummary, ConversationStatus, ConversationRequiredAction

from moio_platform.lib.moio_agent_tools import end_conversation, search_product, create_ticket
from moio_platform.lib.moio_assistant_functions import MoioAssistantTools

from moio_platform.lib.tools import has_time_passed

from central_hub.models import TenantConfiguration
import logging
from chatbot.lib.whatsapp_client_api import WhatsappMessage
from chatbot.core.agents import OrchestratorAgent
from chatbot.core.human_mode_context import append_context_message
from chatbot.models.chatbot_session import ChatbotSession
from moio_platform.core.events import emit_event
from agents import Agent, WebSearchTool, FileSearchTool, function_tool, Runner, RunHooks, AgentOutputSchema, \
    set_default_openai_key, ModelSettings, trace

from datetime import timedelta
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class AgentThread:

    def __init__(self, session):
        self.session = session

    def add_utterance(self, content: str, role: str, author=""):

        start_time = timezone.now()
        if author == "":
            author = role

        try:
            latest_utterance = ChatbotMemory.objects.filter(session=self.session).latest("created")
            print(f"Latest utterance {latest_utterance.content}")

            #  ============================================================
            #   Attempt to stitch two or more rapid utterances coming from the user
            if latest_utterance.role == "user" and role == latest_utterance.role:
                print(f'Last utterance ->{latest_utterance.content} role: {latest_utterance.role}')
                print(f'Merging utterances from ->{content} role: {role}')
                latest_utterance.content = f'{latest_utterance.content} {content}'
                latest_utterance.stitches += 1
                latest_utterance.save()

            else:
                print(f'Last utterance ->{latest_utterance.role}')

                new_utterance = ChatbotMemory(
                    session=self.session,
                    role=role,
                    content=content,
                    author=author
                )
                new_utterance.save()

        #  ============================================================
        except ChatbotMemory.DoesNotExist:

            new_utterance = ChatbotMemory(
                session=self.session,
                role=role,
                content=content,
                author=author

            )
            new_utterance.save()

        from chatbot.serializers import build_message_payload
        try:
            if role == "user":
                chatbot.events.message_received(new_utterance)
            else:
                chatbot.events.message_sent(new_utterance)
        except Exception as e:
            logger.error(e)

        end_time = timezone.now()  # Capture end time
        elapsed_time = end_time - start_time  # Calculate elapsed time
        print("add utterance took {} seconds".format(elapsed_time.total_seconds()))

    def get_full_transcript(self):

        gpt_conversation = []
        for dialog in ChatbotMemory.objects.filter(session=self.session).order_by("created"):
            gpt_dialog = {
                "role": dialog.role,
                "content": dialog.content,
                "created": dialog.created.strftime("%Y-%m-%d %H:%M:%S"),
            }
            gpt_conversation.append(gpt_dialog)
        return gpt_conversation

    def get_latest_user_utterance(self):
        try:
            latest = ChatbotMemory.objects.filter(session=self.session, role="user").latest("created")
            return latest

        except ChatbotMemory.DoesNotExist:
            return None


class MoioAgent:

    def __init__(self, config: TenantConfiguration, contact: Contact):

        self.config = config
        self.contact = contact
        self.additional_instructions = f"This is the info about the user phone:{contact.phone}, name:{contact.fullname}, whatsapp display name: {contact.whatsapp_name}, email:{contact.email}, if some field is missing try to retrieve it. Date {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}"
        self.channel = "whatsapp"
        self.poll_interval = 300
        set_default_openai_key(self.config.openai_api_key)
        start_time = timezone.now()
        try:
            self.current_agent = AgentConfiguration.objects.get(tenant=self.config.tenant, default=True)
        except AgentConfiguration.DoesNotExist:
            raise RuntimeError(f"No Default Agent Configured for {config.tenant}")

        if contact.ctype is not None:

            if contact.ctype.default_agent is not None:
                self.current_agent = contact.ctype.default_agent

        print(f"Default agent is {self.current_agent}")

        try:
            assistant_session = ChatbotSession.objects.get(contact=contact, tenant_id=self.config.tenant_id, active=True, channel=self.channel)

        except ChatbotSession.DoesNotExist:

            assistant_session = ChatbotSession.objects.create(
                tenant_id=self.config.tenant_id,
                contact=contact,
                start=timezone.now(),
                last_interaction=timezone.now(),
                channel=self.channel
            )
            assistant_session.save()

            try:
                emit_event(
                    name="chatbot_session.created",
                    tenant_id=contact.tenant.tenant_code,
                    actor={"type": "system", "id": "moio_agent"},
                    entity={"type": "chatbot_session", "id": str(assistant_session.session)},
                    payload={
                        "session_id": str(assistant_session.session),
                        "contact_id": str(contact.user_id) if getattr(contact, "user_id", None) else None,
                        "contact_name": contact.fullname,
                        "channel": assistant_session.channel,
                        "started_at": assistant_session.start.isoformat() if assistant_session.start else None,
                        "active": bool(assistant_session.active),
                    },
                    source="chatbot",
                )
            except Exception:
                pass

            thread = AgentThread(assistant_session)
            thread.add_utterance(self.additional_instructions, role="system", author="moio")

        except ChatbotSession.MultipleObjectsReturned:

            assistant_session = ChatbotSession.objects.filter(contact=contact, tenant_id=self.config.tenant_id, active=True, channel=self.channel).latest("last_interaction")

        self.assistant_session = assistant_session

    def reply_to_whatsapp_message(self, message: WhatsappMessage):
        set_default_openai_key(self.config.openai_api_key)
        start_time = timezone.now()

        try:
            add_utterance_start_time = timezone.now()

            thread = AgentThread(session=self.assistant_session)
            thread.add_utterance(content=message.raw_message, role='user')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            ag = Agent(
                name=self.current_agent.name,
                instructions=f"{self.current_agent.instructions}",
                model=f"{self.current_agent.model}",
                tools=[end_conversation, search_product, create_ticket],
                #model_settings=ModelSettings(tool_choice="required"),
                # handoffs=[expert_mode],
                # output_type=WhatsAppMessage
            )

            print(f"Session is {self.assistant_session.session}")
            result = asyncio.run(Runner.run(ag, input=json.dumps(thread.get_full_transcript()), context=str(self.assistant_session.session)))

            thread.add_utterance(content=result.final_output, role='assistant', author="")
            return result.final_output

        except Exception as e:
            logger.error(str(e))

    def reply_to_message(self, message):

        set_default_openai_key(self.config.openai_api_key)
        start_time = timezone.now()

        try:
            add_utterance_start_time = timezone.now()

            thread = AgentThread(session=self.assistant_session)
            thread.add_utterance(content=message["content"], role='user')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            ag = Agent(
                name=self.current_agent.name,
                instructions=f"{self.current_agent.instructions}",
                model=f"{self.current_agent.model}",
                tools=[end_conversation, search_product, create_ticket],
                #model_settings=ModelSettings(tool_choice="required"),
                # handoffs=[expert_mode],
                # output_type=WhatsAppMessage
            )

            print(f"Session is {self.assistant_session.session}")
            result = asyncio.run(Runner.run(ag, input=json.dumps(thread.get_full_transcript()), context=str(self.assistant_session.session)))

            thread.add_utterance(content=result.final_output, role='assistant', author="")
            return result.final_output

        except Exception as e:
            logger.error(str(e))

    def internal_command(self, message):
        set_default_openai_key(self.config.openai_api_key)
        start_time = timezone.now()

        try:
            add_utterance_start_time = timezone.now()

            thread = AgentThread(session=self.assistant_session)
            thread.add_utterance(content=message, role='system')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            ag = OrchestratorAgent(self.assistant_session.session)
            print(f"Session is {self.assistant_session.session}")

            result = Runner.run_sync(
                ag.orchestrator_agent,
                input=json.dumps(thread.get_full_transcript()),
                context=str(self.assistant_session.session)
            )

            print(f"final output: {result.final_output}")

            thread.add_utterance(content=result.final_output, role='assistant')
            return result.final_output

        except Exception as e:
            print(e)

    def summarize_conversation(self):

        handler_name = "conversation_summarizer"
        try:
            agent_config = AgentConfiguration.objects.get(tenant=self.config.tenant, name=handler_name)

        except AgentConfiguration.DoesNotExist:
            agent_config = AgentConfiguration.objects.create(tenant=self.config.tenant, name=handler_name)
            agent_config.save()
            raise EnvironmentError(f"Configuration for {handler_name} not found")

        thread = AgentThread(session=self.assistant_session)

        summarizer = Agent(
            name=agent_config.name,
            instructions=agent_config.instructions,
            # tools=[
            #    async_create_ticket,
            #    async_end_conversation
            # ],
            model=agent_config.model,
            # handoffs=[expert_mode],
            # output_type=WhatsAppMessage
        )

        result = Runner.run_sync(
            summarizer,
            input=json.dumps(thread.get_full_transcript()),
            context=str(self.assistant_session.session)
        )
        print(result.final_output)

    def analyze_conversation(self):
        handler_name = "conversation_analyzer"
        try:
            agent_config = AgentConfiguration.objects.get(tenant=self.config.tenant, name=handler_name)

        except AgentConfiguration.DoesNotExist:
            agent_config = AgentConfiguration.objects.create(tenant=self.config.tenant, name=handler_name, enabled=False)
            agent_config.save()

        if agent_config.enabled:
            thread = AgentThread(session=self.assistant_session)
            analyzer = Agent(
                name=agent_config.name,
                instructions=agent_config.instructions,
                model=agent_config.model,
                output_type=ConversationAnalysisModel
            )
            try:
                result = asyncio.run(Runner.run(analyzer, input=json.dumps(thread.get_full_transcript()), context=str(self.assistant_session.session)))
            except RuntimeError as e:

                # No loop exists (e.g., prefork)
                logger.debug(f"No event loop: {e}")
                result = Runner.run(analyzer, input=json.dumps(thread.get_full_transcript()), context=str(self.assistant_session.session))

            print(f"Analysis result status: {result.final_output.status} will {result.final_output.action} message: {result.final_output.message_to_send}")
            if result.final_output.action == ConversationRequiredAction.END_CONVERSATION:

                print(f"Action: END_CONVERSATION")
                thread.add_utterance(content=result.final_output.message_to_send, role='assistant', author=handler_name)
                session = ChatbotSession.objects.get(session=self.assistant_session)
                mt = MoioAssistantTools(session=session)
                mt.end_conversation(result.final_output.summary)

                return result.final_output.message_to_send

            elif result.final_output.action == ConversationRequiredAction.RE_ENGAGE:
                print(f"Action: RE_ENGAGE")
                thread.add_utterance(content=result.final_output.message_to_send, role='assistant', author=handler_name)
                return result.final_output.message_to_send

            elif result.final_output.action == ConversationRequiredAction.PRODUCE_RESPONSE:

                print(f"Action: PRODUCE_RESPONSE")
                thread.add_utterance(content=result.final_output.message_to_send, role='assistant', author=handler_name)
                return result.final_output.message_to_send

            else:
                return None

        else:
            logger.error(f"{handler_name} is not enabled")
            return None


class AgentEngine:

    def __init__(self, config: TenantConfiguration, contact: Contact, started_by="user"):

        self.config = config
        self.contact = contact
        self.additional_instructions = f"This is the info about the user phone:{contact.phone}, name:{contact.fullname}, whatsapp display name: {contact.whatsapp_name}, email:{contact.email}, contact type:{contact.ctype.name} if some field is missing try to retrieve it. Date {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}"
        self.channel = "whatsapp"
        self.poll_interval = 300
        start_time = timezone.now()

        self.agent_list = build_agents_for_tenant(self.config.tenant)  # Aquí se cargan todos los agentes disponibles, las herramientas deben estar cargadas

        try:
            if config.agent_allow_reopen_session :

                limit = timezone.now() - timedelta(minutes=config.agent_reopen_threshold)

                assistant_session = ChatbotSession.objects.get(
                    Q(contact=contact),
                    Q(tenant_id=self.config.tenant_id),
                    Q(channel=self.channel),
                    Q(active=True) |
                    Q(active=False, last_interaction__gte=limit)
                )
                if not assistant_session.active:
                    assistant_session.active = True
                    assistant_session.save(update_fields=['active'])
            else:
                assistant_session = ChatbotSession.objects.get(contact=contact, tenant_id=self.config.tenant_id,
                                                               active=True, channel=self.channel)

        except ChatbotSession.DoesNotExist:

            try:
                default_agent = AgentConfiguration.objects.get(tenant=self.config.tenant, default=True).name

            except AgentConfiguration.DoesNotExist:
                raise RuntimeError(f"No Default Agent Configured for {config.tenant}")

            if contact.ctype is not None:
                if contact.ctype.default_agent is not None:
                    default_agent = contact.ctype.default_agent.name

            print(f"Setting Default agent: {default_agent}")

            assistant_session = ChatbotSession.objects.create(
                tenant_id=self.config.tenant_id,
                contact=contact,
                start=timezone.now(),
                last_interaction=timezone.now(),
                channel=self.channel,
                current_agent=default_agent,
                started_by=started_by,
            )

            assistant_session.context = [{"role": "system", "content": self.additional_instructions}]

            assistant_session.save()

            try:
                emit_event(
                    name="chatbot_session.created",
                    tenant_id=contact.tenant.tenant_code,
                    actor={"type": "system", "id": "moio_agent"},
                    entity={"type": "chatbot_session", "id": str(assistant_session.session)},
                    payload={
                        "session_id": str(assistant_session.session),
                        "contact_id": str(contact.user_id) if getattr(contact, "user_id", None) else None,
                        "contact_name": contact.fullname,
                        "channel": assistant_session.channel,
                        "started_at": assistant_session.start.isoformat() if assistant_session.start else None,
                        "active": bool(assistant_session.active),
                    },
                    source="chatbot",
                )
            except Exception:
                pass

            from chatbot.serializers import build_session_payload
            chatbot.events.session_started(assistant_session)

            thread = AgentThread(assistant_session)
            thread.add_utterance(self.additional_instructions, role="system", author="moio")

        except ChatbotSession.MultipleObjectsReturned:

            assistant_session = ChatbotSession.objects.filter(contact=contact, tenant_id=self.config.tenant_id, active=True, channel=self.channel).latest("last_interaction")

        self.assistant_session = assistant_session

    def reply_to_whatsapp_message(self, message: WhatsappMessage):
        set_default_openai_key(self.config.openai_api_key)
        start_time = timezone.now()
        print(f'Current Agent: {self.assistant_session.current_agent}')
        running_agent = self.agent_list.get(self.assistant_session.current_agent)  # Seleccionar el agente adecuado para la session (el agente por defecto debe asignarse al crear una nueva)

        try:
            add_utterance_start_time = timezone.now()

            thread = AgentThread(session=self.assistant_session)
            thread.add_utterance(content=message.raw_message, role='user')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            context = {
                "session": self.assistant_session,
                "contact": self.contact,
                "config": self.config,
            }
            print(running_agent)

            if self.assistant_session.context is None:
                agent_input = str(message.raw_message)
            else:
                agent_input = self.assistant_session.context + [{"role": "user", "content": str(message.raw_message)}]

            with trace(workflow_name=f"Chat with {self.contact.phone}", group_id=str(self.assistant_session.pk)):
                result = asyncio.run(Runner.run(
                    running_agent,
                    # input=json.dumps(thread.get_full_transcript()),
                    input=agent_input,
                    context=context
                ))  # Ejecutar el agente agregando la thread y el contexto

            print(result.final_output)
            print(f'Last agent: {result.last_agent.name}')
            self.assistant_session.refresh_from_db()

            self.assistant_session.context = result.to_input_list()
            thread.add_utterance(content=result.final_output, role='assistant', author=result.last_agent.name)

            print(f"Session is {self.assistant_session.session}")
            self.assistant_session.current_agent = result.last_agent.name  # Reemplazar con la actualization del agente a cargo de la session
            self.assistant_session.save()

            return result.final_output

        except Exception as e:
            logger.error(str(e))

    def reply_to_message(self, message):
        # Check if human mode is enabled - skip AI response generation but still handle incoming message
        if self.assistant_session.human_mode:
            # Human mode: process incoming message and store in thread, but skip AI response
            thread = AgentThread(session=self.assistant_session)
            media_path = message.get("media")
            context_message = None

            if message["content"] != "":
                thread.add_utterance(content=message["content"], role='user')
                context_message = message["content"]
            elif media_path is not None:
                thread.add_utterance(content=message["media"], role='user')
                context_message = message["media"]
            else:
                thread.add_utterance(content=json.dumps(message), role='user')
                context_message = json.dumps(message)

            self.assistant_session.context = append_context_message(
                self.assistant_session.context,
                "user",
                context_message,
            )
            self.assistant_session.last_interaction = timezone.now()
            self.assistant_session.save(update_fields=["context", "last_interaction"])
            logger.info("Human mode enabled - skipping AI response generation for session %s", self.assistant_session.pk)
            return None

        set_default_openai_key(self.config.openai_api_key)
        logger.info(f'Current Agent: {self.assistant_session.current_agent}')
        running_agent = self.agent_list.get(self.assistant_session.current_agent)  # Seleccionar el agente adecuado para la session (el agente por defecto debe asignarse al crear una nueva)

        try:
            add_utterance_start_time = timezone.now()

            thread = AgentThread(session=self.assistant_session)
            media_path = message.get("media")

            if message["content"] != "":
                thread.add_utterance(content=message["content"], role='user')

            elif media_path is not None:
                thread.add_utterance(content=message["media"], role='user')

            else:
                thread.add_utterance(content=json.dumps(message), role='user')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            context = {
                "session": self.assistant_session,
                "contact": self.contact,
                "config": self.config,
            }

            logger.info("Running Agent")

            if self.assistant_session.context is None:
                agent_input = str(message["content"])
            else:
                agent_input = self.assistant_session.context + [{"role": "user", "content": message["content"]}]

            with trace(workflow_name=f"Chat with {self.contact.phone}", group_id=str(self.assistant_session.pk)):
                result = asyncio.run(Runner.run(
                    running_agent,
                    # input=json.dumps(thread.get_full_transcript()),
                    input=agent_input,
                    context=context
                ))  # Ejecutar el agente agregando la thread y el contexto

            print(result.final_output)
            print(f'Last agent: {result.last_agent.name}')
            self.assistant_session.refresh_from_db()

            self.assistant_session.context = result.to_input_list()
            thread.add_utterance(content=result.final_output, role='assistant', author=result.last_agent.name)

            print(f"Session is {self.assistant_session.session}")
            self.assistant_session.current_agent = result.last_agent.name  # Reemplazar con la actualization del agente a cargo de la session
            self.assistant_session.save()

            return result.final_output

        except Exception as e:
            logger.error(str(e))

    def internal_command(self, message):
        set_default_openai_key(self.config.openai_api_key)
        start_time = timezone.now()

        try:
            add_utterance_start_time = timezone.now()

            thread = AgentThread(session=self.assistant_session)
            thread.add_utterance(content=message, role='system')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            ag = OrchestratorAgent(self.assistant_session.session)
            print(f"Session is {self.assistant_session.session}")

            result = Runner.run_sync(
                ag.orchestrator_agent,
                input=json.dumps(thread.get_full_transcript()),
                context=str(self.assistant_session.session)
            )

            print(f"final output: {result.final_output}")

            thread.add_utterance(content=result.final_output, role='assistant')
            return result.final_output

        except Exception as e:
            print(e)

    def register_outgoing_campaign_message(self, message):
        set_default_openai_key(self.config.openai_api_key)

        try:
            add_utterance_start_time = timezone.now()
            self.assistant_session.context.append({"role": "assistant", "content": message})
            self.assistant_session.save()

            thread = AgentThread(session=self.assistant_session)
            thread.add_utterance(content=message, role='assistant')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            print(f"Session is {self.assistant_session.session}")

        except Exception as e:
            print(e)

    def summarize_conversation(self):

        handler_name = "conversation_summarizer"
        try:
            agent_config = AgentConfiguration.objects.get(tenant=self.config.tenant, name=handler_name)

        except AgentConfiguration.DoesNotExist:
            agent_config = AgentConfiguration.objects.create(tenant=self.config.tenant, name=handler_name)
            agent_config.save()
            raise EnvironmentError(f"Configuration for {handler_name} not found")

        thread = AgentThread(session=self.assistant_session)

        summarizer = Agent(
            name=agent_config.name,
            instructions=agent_config.instructions,
            # tools=[
            #    async_create_ticket,
            #    async_end_conversation
            # ],
            model=agent_config.model,
            # handoffs=[expert_mode],
            # output_type=WhatsAppMessage
        )

        result = Runner.run_sync(
            summarizer,
            input=json.dumps(thread.get_full_transcript()),
            context=str(self.assistant_session.session)
        )
        print(result.final_output)

    def analyze_conversation(self, instruction: str):
        set_default_openai_key(self.config.openai_api_key)
        handler_name = "conversation_analyzer"

        running_agent = self.agent_list.get(handler_name)  # Seleccionar el agente adecuado para la session (el agente por defecto debe asignarse al crear una nueva)

        try:
            add_utterance_start_time = timezone.now()

            thread = AgentThread(session=self.assistant_session)
            thread.add_utterance(content=instruction, role='system')

            elapsed_time = timezone.now() - add_utterance_start_time
            print(f"Time to add utterance:{elapsed_time.total_seconds()}")

            context = {
                "session": self.assistant_session,
                "contact": self.contact,
                "config": self.config,
            }
            print(running_agent)

            if self.assistant_session.context is None:
                agent_input = instruction
            else:
                agent_input = self.assistant_session.context + [{"role": "user", "content": instruction}]

            with trace(workflow_name=f"Analyzing {self.contact.phone}", group_id=str(self.assistant_session.pk)):

                result = asyncio.run(Runner.run(
                    running_agent,
                    # input=json.dumps(thread.get_full_transcript()),
                    input=agent_input,
                    context=context
                ))  # Ejecutar el agente agregando la thread y el contexto

            print(result.final_output)
            print(f'Last agent: {result.last_agent.name}')
            self.assistant_session.refresh_from_db()

            self.assistant_session.context = result.to_input_list()
            thread.add_utterance(content=result.final_output, role='assistant', author=result.last_agent.name)

            print(f"Session is {self.assistant_session.session}")
            self.assistant_session.current_agent = result.last_agent.name  # Reemplazar con la actualization del agente a cargo de la session
            self.assistant_session.save()

            return result.final_output

        except Exception as e:

            logger.error(str(e))


def session_sweep(tenant_id: int):
    config = TenantConfiguration.objects.get(tenant=tenant_id)
    inactive_threshold = config.assistants_inactivity_limit

    sessions = ChatbotSession.objects.filter(
        tenant_id=tenant_id, active=True, channel="whatsapp"
    ).iterator()

    for session in sessions:
        if has_time_passed(session.last_interaction, inactive_threshold):
            try:
                engine = AgentEngine(config, session.contact)
                engine.analyze_conversation("Conversation inactive – consider ending")
            except Exception as e:
                logger.exception(f"Sweep error for session {session.session}: {e}")