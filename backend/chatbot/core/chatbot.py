import ast
import json
import time

from django.utils import timezone
from openai import OpenAI

from chatbot.models.chatbot_configuration import ChatbotConfiguration
from chatbot.models.chatbot_session import ChatbotMemory
from chatbot.models.chatbot_session import ChatbotSession
from chatbot.core.messenger import Messenger
from chatbot.core.human_mode_context import append_context_message

from crm.models import Contact
from moio_platform.lib.tools import has_time_passed
from moio_platform.lib.moio_assistant_functions import MoioAssistantTools
from moio_platform.lib.openai_gpt_api import full_chat_reply, summarize_chat
from portal.models import TenantConfiguration
import logging
from celery import shared_task, current_task
from django.conf import settings
from chatbot.lib.whatsapp_client_api import WhatsappMessage
from chatbot.core.agents import OrchestratorAgent
import asyncio

from agents import Agent, WebSearchTool, FileSearchTool, function_tool, Runner, RunHooks, AgentOutputSchema, set_default_openai_key

logger = logging.getLogger(__name__)


class MemoryThread:
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

        end_time = timezone.now()  # Capture end time
        elapsed_time = end_time - start_time  # Calculate elapsed time
        print("add utterance took {} seconds".format(elapsed_time.total_seconds()))

    def load_chat_transcript(self):

        gpt_conversation = []
        for dialog in ChatbotMemory.objects.filter(session=self.session).order_by("created"):
            gpt_dialog = {
                "role": dialog.role,
                "content": dialog.content
            }
            gpt_conversation.append(gpt_dialog)
        return gpt_conversation

    def get_latest_user_utterance(self):
        try:
            latest = ChatbotMemory.objects.filter(session=self.session, role="user").latest("created")
            return latest

        except ChatbotMemory.DoesNotExist:
            return None


class Chatbot:

    def __init__(self, contact: Contact, channel: str, tenant):

        self.tenant_configuration = TenantConfiguration.objects.get(tenant=tenant)
        self.tenant = tenant
        self.contact = contact
        self.last_assistant_message = ''
        self.channel = channel
        self.intent = None
        try:
            self.chatbot_configuration = ChatbotConfiguration.objects.get(tenant=tenant)
            self.directive = self.chatbot_configuration.chatbot_prompt
            self.summarizer_prompt = self.chatbot_configuration.summarizer_prompt

        except ChatbotConfiguration.DoesNotExist:
            self.directive = "Chatbot not configured, be polite don't respond to any question, simply say, I will ask my admin to get in touch with you soon"
            self.summarizer_prompt = "Summarize the conversation and return in json"

        self._busy = False
        self._multi_message = False

        try:
            self.session = ChatbotSession.objects.get(contact=contact, active=True, tenant=self.tenant)
            print(f'session: {self.session}')

        except ChatbotSession.MultipleObjectsReturned:
            self.session = ChatbotSession.objects.filter(contact=contact, active=True, tenant=self.tenant).latest("start")
            print(f'session: {self.session}')

        except ChatbotSession.DoesNotExist:
            self.session = ChatbotSession(
                contact=contact,
                start=timezone.now(),
                last_interaction=timezone.now(),
                started_by='user',
                channel=channel,
                active=True,
                busy=False,
                multi_message=False,
                experience=self.chatbot_configuration.experience
            )
            self.session.save()
            self._setup_conversation()

        print(f"This machine is now in session: {self.session} ")

    def _setup_conversation(self):

        print(f"Setting up the conversation for the first time..")

        user_data = {
            "fecha": timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "whatsapp_name": self.contact.whatsapp_name,
            "fullname": self.contact.fullname,
            "phone": self.contact.phone,
            "email": self.contact.email
        }

        assistant_setup = f"""
        Estamos iniciando una nueva conversación con este contacto.
        Estos son los datos que tenemos: {json.dumps(user_data)}"""

        memory_thread = MemoryThread(self.session)
        memory_thread.add_utterance(self.directive, role="system")
        memory_thread.add_utterance(assistant_setup, role='system')

    def reply_to_this(self, user_said):

        # Check if human mode is enabled - skip AI response generation but still handle incoming message
        if self.session.human_mode:
            # Human mode: process incoming message and store in memory, but skip AI response
            memory_thread = MemoryThread(self.session)
            memory_thread.add_utterance(user_said, "user")
            self.session.context = append_context_message(self.session.context, "user", user_said)
            self.session.last_interaction = timezone.now()
            self.session.save(update_fields=["context", "last_interaction"])
            logger.info("Human mode enabled - skipping AI response generation for session %s", self.session.pk)
            return None

        memory_thread = MemoryThread(self.session)
        memory_thread.add_utterance(user_said, "user")
        chat = memory_thread.load_chat_transcript()

        time.sleep(10)  # Pauses execution for 10 seconds

        latest = memory_thread.get_latest_user_utterance()
        if latest.stitches > latest.skipped:
            latest.skipped += 1
            latest.save()
            print(f"Skipping response {latest.stitches} stitches {latest.skipped} skipped ")
            return None

        else:

            if self.session.context is not None:
                compressed_conversation = json.dumps(self.session.context)

                chat = [
                    {"role": "system", "content": self.directive},
                    {"role": "system", "content": compressed_conversation},
                    {"role": "user", "content": memory_thread.get_latest_user_utterance().content}
                ]

            try:

                full_reply = json.loads(full_chat_reply(chat=chat, openai_api_key=self.tenant_configuration.openai_api_key, model=self.tenant_configuration.openai_default_model))
                print(full_reply)

                reply = full_reply["next_assistant_utterance"]

                memory_thread.add_utterance(reply, "assistant", author=self.chatbot_configuration.experience)
                self.last_assistant_message = reply
                self.session.context = full_reply
                self.session.last_interaction = timezone.now()

                if full_reply["conversation_ended"]:
                    print("conversation ended")
                    self.session.active = False
                    full_chat = memory_thread.load_chat_transcript()

                    self.session.final_summary = summarize_chat(full_chat, self.summarizer_prompt, openai_api_key=self.tenant_configuration.openai_api_key,
                                                                model=self.tenant_configuration.openai_default_model)
                    self.session.end = timezone.now()

                self.session.save()

            except Exception as e:
                print(e)
                reply = "Ocurrió un problema"

            return reply


class MoioAssistant:

    def __init__(self, openai_key, contact, tenant_id, default_assistant_id, channel):

        self.client = OpenAI(api_key=openai_key)
        self.contact = contact
        self.assistant_id = default_assistant_id
        self.additional_instructions = f"This is the info about the user phone:{contact.phone}, name:{contact.fullname}, whatsapp display name: {contact.whatsapp_name}, email:{contact.email}, if some field is missing try to retrieve it. Date {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}"
        self.channel = channel
        self.poll_interval = 300

        try:
            assistant_session = ChatbotSession.objects.get(contact=contact, tenant_id=tenant_id, active=True, channel=channel)

            self.thread = self.client.beta.threads.retrieve(assistant_session.thread_id)
            self.assistant = self.client.beta.assistants.retrieve(assistant_session.assistant_id)

        except ChatbotSession.DoesNotExist:
            print("Session does not exist")

            self.thread = self.client.beta.threads.create()
            self.assistant = self.client.beta.assistants.retrieve(default_assistant_id)

            assistant_session = ChatbotSession(
                tenant_id=tenant_id,
                contact=contact,
                thread_id=self.thread.id,
                assistant_id=self.assistant.id,
                start=timezone.now(),
                last_interaction=timezone.now(),
                channel=self.channel,

            )
            assistant_session.save()

        except ChatbotSession.MultipleObjectsReturned:
            print("Multiple Session already exists")

            assistant_session = ChatbotSession.objects.filter(contact=contact, tenant_id=tenant_id, active=True, channel=self.channel).latest("last_interaction")

        except Exception as e:
            logger.error(str(e))
            raise e

        self.assistant_session = assistant_session
        self.tools = MoioAssistantTools(session=assistant_session)

    def _function_calls(self, run_instance, thread_id, tools):

        tool_outputs = []
        for tool in run_instance.required_action.submit_tool_outputs.tool_calls:
            # tool is the variable of any function name to be run and args are the list of arguments for that specific function
            # the name of the function and args to be run is selected by the agent
            print(f"Need output from {tool.function.name}")
            tool_function = getattr(tools, tool.function.name)
            args = ast.literal_eval(tool.function.arguments)

            response_from_tool = {
              "tool_call_id": tool.id,
              "output": tool_function(**args),
              # here we execute the function with the parameters and add the result to the tools_outputs list with their corresponding tool_call_id
            }

            tool_outputs.append(response_from_tool)
            print(tool_outputs)

        print("outputs submitted")

        return self.client.beta.threads.runs.submit_tool_outputs_and_poll(
            thread_id=thread_id,
            run_id=run_instance.id,
            tool_outputs=tool_outputs,
            poll_interval_ms=self.poll_interval,
        )

    def retrieve(self, assistant_id):
        assistant = self.client.beta.assistants.retrieve(assistant_id=assistant_id)
        return assistant

    def set_assistant(self, assistant_id):
        self.assistant_id = assistant_id

    def reply_to_this(self, message_content: str):
        """
        add the new message to the thread
        # memory = self.assistant_session.memory_thread.

        Status	            Definition

        queued:	            When Runs are first created or when you complete the required_action, they are moved to a queued status. They should almost immediately move to in_progress.
        in_progress:	    While in_progress, the Assistant uses the model and tools to perform steps. You can view progress being made by the Run by examining the Run Steps.
        completed:	        The Run successfully completed! You can now view all Messages the Assistant added to the Thread, and all the steps the Run took. You can also continue the conversation by adding more user Messages to the Thread and creating another Run.
        requires_action:	When using the Function calling tool, the Run will move to a required_action state once the model determines the names and arguments of the functions to be called. You must then run those functions and submit the outputs before the run proceeds. If the outputs are not provided before the expires_at timestamp passes (roughly 10 minutes past creation), the run will move to an expired status.
        expired:        	This happens when the function calling outputs were not submitted before expires_at and the run expires. Additionally, if the runs take too long to execute and go beyond the time stated in expires_at, our systems will expire the run.
        cancelling:     	You can attempt to cancel an in_progress run using the Cancel Run endpoint. Once the attempt to cancel succeeds, status of the Run moves to cancelled state. Cancellation is attempted but not guaranteed.
        cancelled:      	Run was successfully cancelled.
        failed_     	    You can view the reason for the failure by looking at the last_error object in the Run. The timestamp for the failure will be recorded under failed_at.
        incomplete:     	Run ended due to max_prompt_tokens or max_completion_tokens reached. You can view the specific reason by looking at the incomplete_details object in the Run.

        :param message_content:
        :return:

        """

        # Check if human mode is enabled - skip AI response generation but still handle incoming message
        if self.assistant_session.human_mode:
            # Human mode: process incoming message and store in memory, but skip AI response
            memory_thread = MemoryThread(session=self.assistant_session)
            memory_thread.add_utterance(content=message_content, role='user')
            try:
                self.client.beta.threads.messages.create(
                    thread_id=self.thread.id,
                    role="user",
                    content=message_content
                )
            except Exception:
                logger.exception("Failed to append human-mode user message to thread %s", self.thread.id)
            self.assistant_session.context = append_context_message(
                self.assistant_session.context,
                "user",
                message_content,
            )
            self.assistant_session.last_interaction = timezone.now()
            self.assistant_session.save(update_fields=["context", "last_interaction"])
            logger.info("Human mode enabled - skipping AI response generation for session %s", self.assistant_session.pk)
            return None

        start_time = timezone.now()

        try:

            memory_thread = MemoryThread(session=self.assistant_session)
            memory_thread.add_utterance(content=message_content, role='user')

            logger.info("reply_to_this started for: %s", self.thread.id)

            for current_run in self.client.beta.threads.runs.list(self.thread.id):

                if current_run.status not in ['completed', 'cancelled', 'expired', 'incomplete', 'failed']:

                    self.client.beta.threads.runs.poll(thread_id=self.thread.id, run_id=current_run.id)
                    logger.error(f"Im inside current run {current_run.id}:{current_run.status}")

                logger.info(current_run.usage)

            thread_message = self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role="user",
                content=message_content
            )

            # Execute the thread with the new message to produce a new reply
            run = self.client.beta.threads.runs.create_and_poll(
                thread_id=self.thread.id,
                assistant_id=self.tools.assistant_id,
                additional_instructions=self.additional_instructions,
                poll_interval_ms=self.poll_interval,
            )

            while run.status != "completed":
                print(f"Run Status: {run.status}, run id: {run.id}, thread_id: {run.thread_id}")
                if run.required_action.type == "submit_tool_outputs":
                    # When functions are enabled, a tool call can be triggered and will wait for an input to continue
                    run = self._function_calls(
                        run_instance=run,
                        tools=self.tools,
                        thread_id=self.thread.id
                    )

            print(f"Run Status: {run.status}, run id: {run.id}, thread_id: {run.thread_id}")

            if run.status == "completed":

                thread_messages = self.client.beta.threads.messages.list(
                    thread_id=self.thread.id,
                    order="asc",
                    limit=100
                )

                reply_content = []
                for message in thread_messages.data:
                    if message.role == "assistant" and message.created_at > thread_message.created_at:
                        # Solo mostrar mensajes del assistant creados despues del input  message.role == "assistant" and message.created_at > thread_message.created_at

                        memory_thread.add_utterance(message.content[0].text.value, role='assistant')

                        logger.debug("Message status:%s", message.status)
                        if message.status == "incomplete":
                            logger.error("reason: %s", message.incomplete_details.reason)

                        reply_content.append(message.content[0].text.value)
                if len(reply_content) == 0:
                    logger.error("No content to send")
                logger.info("reply_to_this ended for: %s", self.thread.id)

                end_time = timezone.now()  # Capture end time
                elapsed_time = end_time - start_time  # Calculate elapsed time
                print("Reply_to_this took {} seconds".format(elapsed_time.total_seconds()))
                self.assistant_session.last_interaction = end_time
                self.assistant_session.save()

                return reply_content

            else:
                logger.error(f"Run {run.id} has status {run.status}")
                return []

        except Exception as e:
            logger.error(str(e))
            return []

    def wake_or_kill(self):
        print(f"Wake or Kill {self.assistant_session.session} {self.assistant_session.contact}")

        ######


        ######

        try:
            wok_message_content = """Wake or Kill Message: Conversation is not progressing. 
                    If an answer from your my side is needed, I will produce it. 
                    If I sent an answer but the user did not reply i will end_conversation gently.
                    """

            memory_thread = MemoryThread(session=self.assistant_session)
            memory_thread.add_utterance("Wake or Kill", role='system', author=self.assistant_session.assistant_id)

            for current_run in self.client.beta.threads.runs.list(self.thread.id, limit=100):
                print(f'run id: {current_run.id} | run status: {current_run.status} | incomplete details: {current_run.incomplete_details}')
                if current_run.status == "in_progress":
                    self.client.beta.threads.runs.poll(self.thread.id, current_run.id)

            wake_or_kill_message = self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role="assistant",
                content=wok_message_content
            )

            run = self.client.beta.threads.runs.create_and_poll(
                thread_id=self.thread.id,
                assistant_id=self.tools.assistant_id,
                poll_interval_ms=self.poll_interval
            )

            if run.status == "completed":
                print(f'run status: {run.status}')

            else:
                while run.status != "completed":
                    if run.required_action.type == "submit_tool_outputs":
                        # When functions are enabled, a tool call can be triggered and will wait for an input to continue
                        run = self._function_calls(
                            run_instance=run,
                            tools=self.tools,
                            thread_id=self.thread.id
                        )
                    else:
                        print(f'run status: {run.status}')

            thread_messages = self.client.beta.threads.messages.list(
                thread_id=self.thread.id,
                order="asc",
                limit=100
            )

            reply_content = []
            for message in thread_messages.data:
                if message.role == "assistant" and message.created_at > wake_or_kill_message.created_at:
                    # Solo mostrar mensajes del assistant creados después del input  message.role == "assistant" and message.created_at > thread_message.created_at

                    memory_thread.add_utterance(message.content[0].text.value, role='assistant')
                    reply_content.append(message.content[0].text.value)
                    print(message.content[0].text.value)

            return reply_content

        except Exception as e:
            raise RuntimeError(e)

    def analyze_conversation(self):

        print(f"Analyzing conversation {self.assistant_session.session} {self.assistant_session.contact}")
        try:

            # "content": "Analyze status of conversation and grade it as: pending_assistant_response, user_stopped_answering, assistant_producing_repetitive_utterances, assistant_has_attempted_to_re_engage_once"
            for current_run in self.client.beta.threads.runs.list(self.thread.id, limit=100):
                print(f'run id: {current_run.id} | run status: {current_run.status} | incomplete details: {current_run.incomplete_details}')
                if current_run.status == "in_progress":
                    self.client.beta.threads.runs.poll(self.thread.id, current_run.id)

            run = self.client.beta.threads.runs.create_and_poll(
                thread_id=self.thread.id,
                assistant_id=self.tools.assistant_id,
                poll_interval_ms=self.poll_interval,

            )

            if run.status == "completed":
                print(f'run status: {run.status}')

            else:
                while run.status != "completed":
                    if run.required_action.type == "submit_tool_outputs":
                        # When functions are enabled, a tool call can be triggered and will wait for an input to continue
                        run = self._function_calls(
                            run_instance=run,
                            tools=self.tools,
                            thread_id=self.thread.id
                        )
                    else:
                        print(f'run status: {run.status}')

            thread_messages = self.client.beta.threads.messages.list(
                thread_id=self.thread.id,
                order="asc",
                limit=100
            )

            reply_content = []
            for message in thread_messages.data:
                if message.role == "assistant":
                    # Solo mostrar mensajes del assistant creados después del input  message.role == "assistant" and message.created_at > thread_message.created_at

                    print(message.content[0].text.value, message.created_at)


        except Exception as e:
            raise RuntimeError(e)

    def get_available_assistants(self):
        assistants = self.client.beta.assistants.list()
        return assistants

    def get_response_format(self):
        print(self.assistant.response_format.type)
        return self.assistant.response_format.type

    def internal_command(self, message_content):
        pass








