import logging
from django.dispatch import Signal

from chatbot.core.messenger import Messenger
from agents import Agent, WebSearchTool, FileSearchTool, function_tool, Runner, RunHooks, AgentOutputSchema, set_default_openai_key, FunctionTool,  RunContextWrapper
from chatbot.models.agent_session import AgentSession
import asyncio
from asgiref.sync import sync_to_async
from moio_platform.lib.moio_assistant_functions import MoioAssistantTools

# Define a custom signal
comfort_message = Signal()

logger = logging.getLogger(__name__)


@function_tool
async def search_product(context_wrapper: RunContextWrapper, search_term: str):
    """
    Search products that match the user intent
    :param search_term: search term to look for will be converted to embedding for semantic search
    """

    session = await sync_to_async(AgentSession.objects.get)(pk=context_wrapper.context)
    mt = MoioAssistantTools(session=session)
    return await sync_to_async(mt.search_product)(search_term)


@function_tool
async def create_ticket(context_wrapper: RunContextWrapper, description: str, service: str):
    """
    Any requirement from the user that cannot be solved by delivering available information, or by acquiring data form the available tools will create a ticket
    In the same language of the conversation.
    :param service: one of "Customer Service", "Sales", "Tech Support"
    """
    session = await sync_to_async(AgentSession.objects.get)(pk=context_wrapper.context)
    mt = MoioAssistantTools(session=session)
    return await sync_to_async(mt.create_ticket)(description, service)


@function_tool
async def end_conversation(context_wrapper: RunContextWrapper, conversation_summary: str):
    """
    Use when the conversation has reached a point where it needs to end, user seems to end it, or the conversation reaches some inconclusive status
    It's a critical function that needs to be used appropriately to ensure the best user experience.
    All conversations need to use it at some point.
    :param conversation_summary: A summary of the conversation, include important details like, search terms, recommendations provided, user mood. In the same language of the conversation
    """
    print("running end_conversation")

    session = await sync_to_async(AgentSession.objects.get)(pk=context_wrapper.context)
    mt = MoioAssistantTools(session=session)

    return await sync_to_async(mt.end_conversation)(conversation_summary)

