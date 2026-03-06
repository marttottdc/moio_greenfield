import inspect
import json
import os
import re
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor

from typing import List, Optional, Tuple, Dict, Any
import heapq
import math

import pytz
from asgiref.sync import async_to_sync
from django.core.serializers.json import DjangoJSONEncoder
from django.db import close_old_connections
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from pydantic import BaseModel, Field, RootModel
from datetime import time

from django.utils import timezone
from pgvector.django.functions import L2Distance, CosineDistance

import chatbot.events
from crm.lib.woocommerce_api import WooCommerceAPI

from crm.models import Stock, ProductVariant, Product, Tag, EcommerceOrder, ActivityRecord, KnowledgeItem, \
    VisibilityChoices, Ticket, Deal, Pipeline, PipelineStage

from moio_platform.lib.google_maps_api import GoogleMapsApi, haversine
from moio_platform.lib.wordpress_api import WordPressAPIClient
from moio_platform.lib.openai_gpt_api import MoioOpenai
from portal.models import TenantConfiguration, PortalConfiguration
from django.dispatch import receiver
from django.dispatch import Signal
from chatbot.core.messenger import Messenger
from agents import FunctionTool, RunContextWrapper, function_tool
from crm.models import Contact
import asyncio
import functools, asyncio, concurrent.futures
from crm.models import ContactType

from datetime import datetime
from django.utils import timezone
from crm.services.activity_service import create_activity, query_activities
from django.contrib.auth import get_user_model

UserModel = get_user_model()

# Define a custom signal
comfort_message = Signal()

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# One shared thread-pool for the whole process                                #
# Tune max_workers as you like; cpu_count()*5 is a common async IO value      #
# --------------------------------------------------------------------------- #
_executor = ThreadPoolExecutor(max_workers=os.cpu_count() * 5)


# --------------------------------------------------------------------------- #
# Internal helper: guarantees DB hygiene in *any* thread                      #
# --------------------------------------------------------------------------- #
def _call_func(func, args, kwargs):
    """
    Run `func(*args, **kwargs)` with Django DB connections closed
    before *and* after, so the thread never hands Celery a stale cursor.
    """
    close_old_connections()
    try:
        return func(*args, **kwargs)
    finally:
        close_old_connections()


# --------------------------------------------------------------------------- #
# Public decorator                                                             #
# --------------------------------------------------------------------------- #


def safe_function_tool(fn=None,
                       *,
                       name: str | None = None,
                       description: str | None = None):
    """
    Wrap a synchronous function so it can be registered as an OpenAI Agents tool
    and called safely from *both* async and sync contexts. Now with automatic
    Django-DB connection cleanup for Celery --pool=threads, prefork, etc.
    """

    def decorator(func):

        @function_tool(
            name_override=name,
            description_override=description,
            failure_error_function=None,
            strict_mode=True,
        )
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                loop = asyncio.get_running_loop()
                if asyncio.current_task(loop=loop):
                    # --- async path: off-load to executor thread -------------
                    logger.debug("safe_tool[%s]: async path", func.__name__)
                    return await loop.run_in_executor(_executor, _call_func,
                                                      func, args, kwargs)
            except RuntimeError:
                # No running loop ⇒ we're already in a plain thread / process
                pass

            # --- sync path ---------------------------------------------------
            logger.debug("safe_tool[%s]: sync path", func.__name__)
            return _call_func(func, args, kwargs)

        return wrapper

    return decorator(fn) if callable(fn) else decorator


def get_function_spec(func):
    func_name = func.__name__

    # Extract the docstring
    doc = inspect.getdoc(func) or ""
    # Function description (first line of the docstring)
    func_description = doc.split("\n")[0].strip() if doc else ""

    required = []
    properties = {}

    # Extract arguments and return descriptions from docstring
    args_match = re.search(r"Args:\s*(.*?)(Returns:|$)", doc, re.DOTALL)
    args_section = args_match.group(1).strip() if args_match else None

    # Parse argument descriptions from docstring
    param_descriptions = {}

    if args_section:
        for line in args_section.split("\n"):
            line = line.strip()
            if ":" in line:
                param_name, param_desc = line.split(":", 1)
                param_descriptions[param_name.strip()] = param_desc.strip()

    # Extract parameters using inspect
    sig = inspect.signature(func)

    for param_name, param in sig.parameters.items():

        if param_name != 'self':

            if param.default is param.empty:
                required.append(param_name)

            properties[param_name] = {
                "type": "string",  # param_type,
                "description": param_descriptions.get(param_name.strip(), "")
            }

    data = {
        "type": "function",
        "function": {
            "name": f"{func_name}",
            "description": f"{func_description}",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            },
        }
    }

    return data


def get_named_period(period_name, date_format="%Y-%m-%d"):
    current_date = timezone.localtime(timezone.now())

    if period_name.lower() == "month to date":
        start_date = current_date.replace(day=1,
                                          hour=0,
                                          minute=0,
                                          second=0,
                                          microsecond=0)
        end_date = current_date

    elif period_name.lower() == "year to date":
        start_date = current_date.replace(month=1,
                                          day=1,
                                          hour=0,
                                          minute=0,
                                          second=0,
                                          microsecond=0)
        end_date = current_date

    else:
        raise ValueError(f"Period '{period_name}' is not recognized")

    # Format the start and end dates
    start_date_formatted = start_date.strftime(date_format)
    end_date_formatted = end_date.strftime(date_format)

    return start_date_formatted, end_date_formatted


@receiver(comfort_message)
def comfort_message_handler(sender, message, tenant_id, phone, **kwargs):
    config = TenantConfiguration.objects.get(tenant=tenant_id)
    channel = kwargs.get('channel', "whatsapp")
    moio_messenger = Messenger(channel=channel,
                               config=config,
                               client_name="comfort")
    moio_messenger.just_reply(message, phone)

    logger.error(f"Sending comfort message {sender}: {message}")


def assign_assistant(ctx: RunContextWrapper) -> str:
    """
    After reviewing the available assistants, return the id of the best match  to continue with the conversation
    """

    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    return "main agent"


@safe_function_tool
def send_comfort_message(ctx: RunContextWrapper, message: str):
    """
        Send a comfort message to the user to inform that you are performing something that may take time
        This message will be sent as a reassurance to the user that you are working on the request.
        :param message: a nice, short message.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    moio_messenger = Messenger(channel=session.channel,
                               config=config,
                               client_name="comfort")
    moio_messenger.just_reply(message, contact.phone)

    logger.error(f"Sending comfort message {message}")
    return f"message sent: {message}"


@safe_function_tool
def search_product(ctx: RunContextWrapper, search_term: str) -> List[dict]:
    """
    Look up products matching `search_term`.

    • First run a simple OR search (JSON blob, name, description).
    • If it yields zero rows, split the term into words and require EACH
      word to appear somewhere (AND of per-word ORs).
    • Return a WhatsApp-ready catalog list.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    try:
        comfort_message.send(sender="search_product",
                             message="Buscando…",
                             tenant_id=session.tenant_id,
                             phone=contact.phone,
                             channel=session.channel)
    except Exception as e:
        logger.error(str(e))
        return []

    base_qs = (Product.objects.annotate(
        attr_text=Cast("attributes", TextField())).filter(
            tenant=config.tenant))

    # ---------- 1) full-string search ----------
    flat_q = (Q(attr_text__icontains=search_term)
              | Q(name__icontains=search_term)
              | Q(description__icontains=search_term))

    products = list(base_qs.filter(flat_q)[:50])  # hard-limit if you like
    if not products:
        # ---------- 2) fallback: AND of words ----------
        words = [w for w in search_term.split() if w]
        if words:
            word_q = Q()
            for w in words:
                word_block = (Q(attr_text__icontains=w) | Q(name__icontains=w)
                              | Q(description__icontains=w))
                word_q &= word_block
            products = list(base_qs.filter(word_q)[:50])

    # ---------- 3) build WhatsApp catalog ----------
    catalog = [{
        "catalog_id": config.whatsapp_catalog_id,
        "id": p.fb_product_id,
        "sku": p.sku,
        "name": p.name,
        "price": p.price,
        "url": p.permalink,
        "attributes": p.attributes,
    } for p in products]
    return catalog


@safe_function_tool
def search_product_by_tag(ctx: RunContextWrapper, search_term: str) -> json:
    """
    Search products that match the user intent, if there are several matches it is convenient to ask the user to disambiguate before presenting the results
    :param ctx:
    :param search_term: in the context of the conversation, what is the user searching for ?

    """
    print(f"Search by tag: {search_term}")
    ###################################################
    #
    #   BE Explicit about attributes in the prompt but keep the search generic for any customer model
    #
    #   prods2 = Product.objects.filter(attributes__Ampers__contains="75 AMP")
    #
    #   prods2 = Product.objects.filter(attributes__has_key="Ampers")
    #
    #   First search for the TAG and then filter by confirmed tag
    #   prods2 = Product.objects.filter(tags__name__icontains='toyota corolla')
    #
    #############################################
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    try:
        comfort_message.send(sender="search_product",
                             message="Buscando...",
                             tenant_id=session.tenant_id,
                             phone=contact.phone,
                             channel=session.channel)
    except Exception as e:
        logger.error(str(e))
        return e

    matches = Tag.objects.filter(tenant=config.tenant,
                                 name__icontains=search_term)

    if matches.count() == 0:

        # ============ Semantic Search ===================================================
        mo = MoioOpenai(api_key=config.openai_api_key,
                        default_model=config.openai_default_model)
        search_term_embedding = mo.get_embedding(search_term)

        matches = Tag.objects.filter(tenant=config.tenant).order_by(
            L2Distance('embedding', search_term_embedding)).annotate(
                l2_distance=L2Distance('embedding', search_term_embedding),
                cos_distance=CosineDistance(
                    'embedding',
                    search_term_embedding)).filter(l2_distance__lt=1.2)[:5]

    results = []
    disambiguation_matches = []
    for match in matches:
        recommended_products = []
        for item in match.products.filter():
            product = {
                'catalog_id': config.whatsapp_catalog_id,
                'id': item.fb_product_id,
                'sku': item.sku,
                'name': item.name,
                # 'description': item.description,
                'price': item.price,
                'url': item.permalink,
            }
            recommended_products.append(product)

            result_item = {
                "search_match": match.name,
                #   "l2_distance": match.l2_distance,
                #   "cosine_distance": match.cos_distance,
                "recommended_products": recommended_products,
                "recommended_message_type": "multi_product_message"
            }
            results.append(result_item)

    if len(results) > 1:
        recommendation = {
            "disambiguation_required": True,
            "instruction":
            "which of all search matches is the one the user was referring to ? Make sure",
            "results": results
        }
        print(recommendation)
        return recommendation
    else:
        return results


@safe_function_tool
def get_full_product_catalog(ctx: RunContextWrapper, search_attr: str,
                             search_term: str):
    """
    Get a full catalog data, use the results to deliver the best possible result
    :param ctx:
    :param search_attr: one of the attrs mentioned by the user or provided in the prompt
    :param search_term: search term to look for will be converted to embedding for semantic search

    """
    ###################################################
    #
    #   BE Explicit about attributes in the prompt but keep the search generic for any customer model
    #
    #   prods2 = Product.objects.filter(attributes__Ampers__contains="75 AMP")
    #
    #   prods2 = Product.objects.filter(attributes__has_key="Ampers")
    #
    #   First search for the TAG and then filter by confirmed tag
    #   prods2 = Product.objects.filter(tags__name__icontains='toyota corolla')
    #
    #############################################

    session = ctx.context.get("session")
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    try:
        comfort_message.send(sender="search_product",
                             message="Búsqueda avanzada...",
                             tenant_id=session.tenant_id,
                             phone=contact.phone,
                             channel=session.channel)
    except Exception as e:
        print(e)

    # key must exist in the JSON and its value must contain `search_term`
    dynamic_lookup = {
        f"attributes__{search_attr}__icontains":
        search_term  # or __contains for exact
    }

    products = (
        Product.objects.filter(
            Q(tenant=config.tenant) & Q(attributes__has_key=search_attr)
            &  # key present (PostgreSQL JSON)
            Q(**dynamic_lookup)  # unpack the dynamic part
        ))
    catalog = []

    for item in products:
        product = {
            'catalog_id': config.whatsapp_catalog_id,
            'id': item.fb_product_id,
            'sku': item.sku,
            'name': item.name,
            'price': item.price,
            'description': item.description,
            'url': item.permalink,
            'attributes': json.dumps(item.attributes),
        }
        catalog.append(product)

    return json.dumps(catalog)


@safe_function_tool
def create_ticket(ctx: RunContextWrapper,
                  description: str,
                  service: str = "default"):
    """
    Any requirement from the user that cannot be solved by delivering available information, or by acquiring data form the available tools will create a ticket
    In the same language of the conversation.
    :param ctx:
    :param description:
    :param service: one of "Customer Service", "Sales", "Tech Support"
    :return:
    """

    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    tenant_id = session.tenant_id
    phone = contact.phone
    email = contact.email

    comfort_message.send(sender="search_product",
                         message="Registrando Solicitud",
                         tenant_id=tenant_id,
                         phone=phone,
                         channel=session.channel)

    ticket = Ticket.objects.create(creator=contact,
                                   tenant_id=tenant_id,
                                   description=description,
                                   service=service,
                                   origin_type='chatbot',
                                   origin_session=session,
                                   origin_ref=str(session.session))

    ticket.save()

    if ticket:
        portal_config = PortalConfiguration.objects.first()

        response = {
            "ticket_created": "true",
            "ticket_id": str(ticket.pk),
            "ticket_description": description,
            "ticket_url":
            f"{portal_config.my_url}crm/tickets/public/{ticket.id.__str__()}",
            "recommended_message_type": "interactive_cta"
        }
    else:
        response = {
            "ticket_created": "false",
        }

    return json.dumps(response)


@safe_function_tool
def create_or_update_ticket(ctx: RunContextWrapper,
                            description: str,
                            ticket_id: str = "",
                            service: str = "default",
                            status: str = ""):
    """
    Create a new support ticket or update an existing one. Use this when managing customer requests across a conversation.
    
    This tool is designed for conversations where ticket details may evolve:
    - First call: Create a ticket (leave ticket_id empty) - returns the ticket_id for future updates
    - Subsequent calls: Pass the ticket_id to update the existing ticket instead of creating duplicates
    
    USE THIS TOOL WHEN:
    - The user has a requirement that cannot be solved with available information
    - You need to update ticket details during an ongoing conversation
    - The user provides additional context or changes their request after initial ticket creation
    
    IMPORTANT: Always store and reuse the ticket_id returned from the first call to avoid creating duplicate tickets.
    
    :param description: Description of the issue or request (required)
    :param ticket_id: If provided, updates the existing ticket. If empty, creates a new ticket.
    :param service: One of "Customer Service", "Sales", "Tech Support"
    :param status: Optional status update (e.g., "open", "pending", "resolved")
    
    Returns JSON with action performed (created/updated), ticket_id, and ticket details.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    tenant_id = session.tenant_id
    phone = contact.phone
    email = contact.email

    try:
        comfort_message.send(sender="create_or_update_ticket",
                             message="Procesando solicitud...",
                             tenant_id=tenant_id,
                             phone=phone,
                             channel=session.channel)
    except Exception as e:
        logger.error(str(e))

    existing_ticket = None
    if ticket_id:
        try:
            existing_ticket = Ticket.objects.get(pk=ticket_id, tenant_id=tenant_id)
        except Ticket.DoesNotExist:
            pass

    if existing_ticket:
        existing_ticket.description = description if description else existing_ticket.description
        if service and service != "default":
            existing_ticket.service = service
        if status:
            existing_ticket.status = status
        existing_ticket.save()

        portal_config = PortalConfiguration.objects.first()

        response = {
            "action": "updated",
            "ticket_id": str(existing_ticket.pk),
            "ticket_description": existing_ticket.description,
            "ticket_service": existing_ticket.service,
            "ticket_url": f"{portal_config.my_url}crm/tickets/public/{existing_ticket.id.__str__()}",
            "message": "Ticket has been updated successfully.",
            "recommended_message_type": "text"
        }
    else:
        ticket = Ticket.objects.create(
            creator=contact,
            tenant_id=tenant_id,
            description=description,
            service=service,
            origin_type='chatbot',
            origin_session=session,
            origin_ref=str(session.session)
        )
        ticket.save()

        portal_config = PortalConfiguration.objects.first()

        response = {
            "action": "created",
            "ticket_id": str(ticket.pk),
            "ticket_description": description,
            "ticket_service": service,
            "ticket_url": f"{portal_config.my_url}crm/tickets/public/{ticket.id.__str__()}",
            "message": "Support ticket has been created. Our team will follow up soon.",
            "recommended_message_type": "interactive_cta"
        }

    return json.dumps(response)


@safe_function_tool
def update_ticket(ctx: RunContextWrapper,
                  ticket_id: str,
                  description: str = "",
                  service: str = "default",
                  status: str = ""):
    """
    Update an existing support ticket.

    Use this when you already have a ticket_id and you need to update details without creating duplicates.

    :param ticket_id: Existing ticket id (required)
    :param description: New description (optional)
    :param service: One of "Customer Service", "Sales", "Tech Support" (optional)
    :param status: Optional status update (e.g., "open", "pending", "resolved")

    Returns JSON with action performed, ticket_id, and ticket details.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    tenant_id = session.tenant_id
    phone = contact.phone

    try:
        comfort_message.send(sender="update_ticket",
                             message="Actualizando ticket...",
                             tenant_id=tenant_id,
                             phone=phone,
                             channel=session.channel)
    except Exception as e:
        logger.error(str(e))

    try:
        ticket = Ticket.objects.get(pk=ticket_id, tenant_id=tenant_id)
    except Ticket.DoesNotExist:
        return json.dumps({
            "action": "error",
            "ticket_id": str(ticket_id),
            "message": "Ticket not found.",
            "recommended_message_type": "text"
        })

    if description:
        ticket.description = description
    if service and service != "default":
        ticket.service = service
    if status:
        ticket.status = status
    ticket.save()

    portal_config = PortalConfiguration.objects.first()
    return json.dumps({
        "action": "updated",
        "ticket_id": str(ticket.pk),
        "ticket_description": ticket.description,
        "ticket_service": ticket.service,
        "ticket_url": f"{portal_config.my_url}crm/tickets/public/{ticket.id.__str__()}",
        "message": "Ticket has been updated successfully.",
        "recommended_message_type": "text"
    })


@safe_function_tool
def create_deal(ctx: RunContextWrapper,
                title: str,
                value: str = "0",
                currency: str = "USD",
                priority: str = "medium",
                description: str = "",
                pipeline_name: str = "",
                stage_name: str = ""):
    """
    Create a sales deal/opportunity when the contact expresses clear buying intent or interest in a product/service.
    
    USE THIS TOOL WHEN:
    - The contact asks for a quote, pricing, or proposal
    - The contact expresses intent to purchase ("I want to buy", "I need X units", "send me a quote")
    - The contact is comparing options and needs follow-up from sales
    - A business opportunity is identified that requires sales team attention
    - The contact requests a meeting or call to discuss a purchase
    
    DO NOT USE THIS TOOL WHEN:
    - The contact is just asking general questions or seeking information
    - The contact has a complaint or support issue (use create_ticket instead)
    - There is no clear commercial intent in the conversation
    
    EXTRACTING DEAL INFORMATION:
    - title: Create a descriptive title from the conversation context (e.g., "Interest in Product X - 50 units")
    - value: If the contact mentions quantities or budget, calculate approximate deal value. Use "0" if unknown.
    - priority: Set based on urgency signals:
        * "high" - Contact needs immediate response, mentions deadline, or is ready to buy now
        * "medium" - Standard buying interest, exploring options (default)
        * "low" - Early-stage interest, just gathering information
    - description: Summarize key details from the conversation that sales should know
    
    :param title: Descriptive title for the deal, summarizing the opportunity (required)
    :param value: Estimated deal value as a number string (e.g., "5000"). Use "0" if unknown.
    :param currency: Currency code (USD, EUR, MXN, etc.). Default is USD.
    :param priority: One of "low", "medium", "high". Reflects urgency of the opportunity.
    :param description: Summary of the opportunity with relevant context from the conversation.
    :param pipeline_name: Optional pipeline name if tenant has multiple sales pipelines.
    :param stage_name: Optional starting stage name. Defaults to first stage of pipeline.
    
    Returns JSON with deal_created status, deal_id, and recommended follow-up message type.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    tenant_id = session.tenant_id
    phone = contact.phone

    try:
        deal_value = float(value) if value else 0
    except (ValueError, TypeError):
        deal_value = 0

    priority_map = {"low": "L", "medium": "M", "high": "H"}
    deal_priority = priority_map.get(priority.lower(), "M")

    pipeline = None
    stage = None

    if pipeline_name:
        pipeline = Pipeline.objects.filter(tenant_id=tenant_id,
                                           name__icontains=pipeline_name,
                                           is_active=True).first()

    if not pipeline:
        pipeline = Pipeline.objects.filter(tenant_id=tenant_id,
                                           is_default=True,
                                           is_active=True).first()

    if not pipeline:
        pipeline = Pipeline.objects.filter(tenant_id=tenant_id,
                                           is_active=True).first()

    if pipeline:
        if stage_name:
            stage = PipelineStage.objects.filter(
                pipeline=pipeline, name__icontains=stage_name).first()
        if not stage:
            stage = PipelineStage.objects.filter(
                pipeline=pipeline).order_by('order').first()

    deal = Deal.objects.create(
        tenant_id=tenant_id,
        title=title,
        description=description,
        contact=contact,
        pipeline=pipeline,
        stage=stage,
        value=deal_value,
        currency=currency.upper(),
        priority=deal_priority,
        status='O',
    )

    if deal:
        
        response = {
            "deal_created": "true",
            "deal_id": str(deal.pk),
            "deal_title": title,
            "deal_value": str(deal_value),
            "deal_currency": currency.upper(),
            "deal_priority": priority,
            "pipeline": pipeline.name if pipeline else None,
            "stage": stage.name if stage else None,
            "message":
            "Sales opportunity has been recorded. A sales representative will follow up soon.",
            "recommended_message_type": "text"
        }
    else:
        response = {
            "deal_created": "false",
            "message": "Could not create the deal. Please try again."
        }

    return json.dumps(response)


@safe_function_tool
def create_or_update_deal(ctx: RunContextWrapper,
                          title: str,
                          deal_id: str = "",
                          value: str = "",
                          currency: str = "",
                          priority: str = "",
                          description: str = "",
                          pipeline_name: str = "",
                          stage_name: str = ""):
    """
    Create a new deal or update an existing one. Use this when managing sales opportunities across a conversation.
    
    This tool is designed for conversations where deal details may evolve:
    - First call: Create a deal (leave deal_id empty) - returns the deal_id for future updates
    - Subsequent calls: Pass the deal_id to update the existing deal instead of creating duplicates
    
    USE THIS TOOL WHEN:
    - The contact asks for a quote, pricing, or proposal
    - The contact expresses intent to purchase ("I want to buy", "I need X units")
    - You need to update deal information during an ongoing conversation
    - The contact changes requirements (quantity, budget, priority) after initial deal creation
    
    IMPORTANT: Always store and reuse the deal_id returned from the first call to avoid creating duplicate deals.
    
    :param title: Descriptive title for the deal (required for create, optional for update)
    :param deal_id: If provided, updates the existing deal. If empty, creates a new deal.
    :param value: Estimated deal value as a number string (e.g., "5000"). Leave empty to preserve existing value on update.
    :param currency: Currency code (USD, EUR, MXN, etc.). Leave empty to preserve existing value on update.
    :param priority: One of "low", "medium", "high". Leave empty to preserve existing value on update.
    :param description: Summary of the opportunity. Leave empty to preserve existing value on update.
    :param pipeline_name: Pipeline name. Leave empty to preserve existing value on update.
    :param stage_name: Stage name within the pipeline. Leave empty to preserve existing value on update.
    
    Returns JSON with action performed (created/updated), deal_id, and deal details.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    tenant_id = session.tenant_id
    phone = contact.phone

    try:
        deal_value = float(value) if value else 0
    except (ValueError, TypeError):
        deal_value = 0

    priority_map = {"low": "L", "medium": "M", "high": "H"}

    existing_deal = None
    if deal_id:
        try:
            existing_deal = Deal.objects.get(pk=deal_id, tenant_id=tenant_id)
        except Deal.DoesNotExist:
            pass

    if existing_deal:
        if title:
            existing_deal.title = title
        if description:
            existing_deal.description = description
        if deal_value > 0:
            existing_deal.value = deal_value
        if currency:
            existing_deal.currency = currency.upper()
        if priority:
            existing_deal.priority = priority_map.get(priority.lower(), existing_deal.priority)
        if pipeline_name:
            new_pipeline = Pipeline.objects.filter(tenant_id=tenant_id,
                                                   name__icontains=pipeline_name,
                                                   is_active=True).first()
            if new_pipeline:
                existing_deal.pipeline = new_pipeline
                if stage_name:
                    new_stage = PipelineStage.objects.filter(
                        pipeline=new_pipeline, name__icontains=stage_name).first()
                    if new_stage:
                        existing_deal.stage = new_stage
                    else:
                        existing_deal.stage = PipelineStage.objects.filter(
                            pipeline=new_pipeline).order_by('order').first()
                else:
                    existing_deal.stage = PipelineStage.objects.filter(
                        pipeline=new_pipeline).order_by('order').first()
        elif stage_name and existing_deal.pipeline:
            new_stage = PipelineStage.objects.filter(
                pipeline=existing_deal.pipeline, name__icontains=stage_name).first()
            if new_stage:
                existing_deal.stage = new_stage
        existing_deal.save()

        priority_reverse = {"L": "low", "M": "medium", "H": "high"}
        response = {
            "action": "updated",
            "deal_id": str(existing_deal.pk),
            "deal_title": existing_deal.title,
            "deal_value": str(existing_deal.value),
            "deal_currency": existing_deal.currency,
            "deal_priority": priority_reverse.get(existing_deal.priority, "medium"),
            "pipeline": existing_deal.pipeline.name if existing_deal.pipeline else None,
            "stage": existing_deal.stage.name if existing_deal.stage else None,
            "message": "Deal has been updated successfully.",
            "recommended_message_type": "text"
        }
    else:
        actual_priority = priority if priority else "medium"
        actual_currency = currency.upper() if currency else "USD"
        deal_priority = priority_map.get(actual_priority.lower(), "M")
        
        pipeline = None
        stage = None

        if pipeline_name:
            pipeline = Pipeline.objects.filter(tenant_id=tenant_id,
                                               name__icontains=pipeline_name,
                                               is_active=True).first()

        if not pipeline:
            pipeline = Pipeline.objects.filter(tenant_id=tenant_id,
                                               is_default=True,
                                               is_active=True).first()

        if not pipeline:
            pipeline = Pipeline.objects.filter(tenant_id=tenant_id,
                                               is_active=True).first()

        if pipeline:
            if stage_name:
                stage = PipelineStage.objects.filter(
                    pipeline=pipeline, name__icontains=stage_name).first()
            if not stage:
                stage = PipelineStage.objects.filter(
                    pipeline=pipeline).order_by('order').first()

        deal = Deal.objects.create(
            tenant_id=tenant_id,
            title=title,
            description=description,
            contact=contact,
            pipeline=pipeline,
            stage=stage,
            value=deal_value,
            currency=actual_currency,
            priority=deal_priority,
            status='O',
        )

        response = {
            "action": "created",
            "deal_id": str(deal.pk),
            "deal_title": title,
            "deal_value": str(deal_value),
            "deal_currency": actual_currency,
            "deal_priority": actual_priority,
            "pipeline": pipeline.name if pipeline else None,
            "stage": stage.name if stage else None,
            "message": "Sales opportunity has been recorded. A sales representative will follow up soon.",
            "recommended_message_type": "text"
        }

    return json.dumps(response)


@safe_function_tool
def update_deal(ctx: RunContextWrapper,
                deal_id: str,
                title: str = "",
                value: str = "",
                currency: str = "",
                priority: str = "",
                description: str = "",
                pipeline_name: str = "",
                stage_name: str = ""):
    """
    Update an existing deal/opportunity.

    Use this when you already have a deal_id and you need to update details without creating duplicates.

    :param deal_id: Existing deal id (required)
    :param title: New title (optional)
    :param value: New estimated deal value as a number string (optional)
    :param currency: Currency code (USD, EUR, MXN, etc.) (optional)
    :param priority: One of "low", "medium", "high" (optional)
    :param description: New description (optional)
    :param pipeline_name: Pipeline name (optional)
    :param stage_name: Stage name within pipeline (optional)

    Returns JSON with action performed, deal_id, and deal details.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    tenant_id = session.tenant_id
    phone = contact.phone

    try:
        comfort_message.send(sender="update_deal",
                             message="Actualizando oportunidad...",
                             tenant_id=tenant_id,
                             phone=phone,
                             channel=session.channel)
    except Exception as e:
        logger.error(str(e))

    try:
        deal = Deal.objects.get(pk=deal_id, tenant_id=tenant_id)
    except Deal.DoesNotExist:
        return json.dumps({
            "action": "error",
            "deal_id": str(deal_id),
            "message": "Deal not found.",
            "recommended_message_type": "text"
        })

    deal_value = None
    if value:
        try:
            deal_value = float(value)
        except (ValueError, TypeError):
            return json.dumps({
                "action": "error",
                "deal_id": str(deal_id),
                "message": "Invalid deal value.",
                "recommended_message_type": "text"
            })

    priority_map = {"low": "L", "medium": "M", "high": "H"}

    if title:
        deal.title = title
    if description:
        deal.description = description
    if deal_value is not None:
        deal.value = deal_value
    if currency:
        deal.currency = currency.upper()
    if priority:
        deal.priority = priority_map.get(priority.lower(), deal.priority)

    if pipeline_name:
        new_pipeline = Pipeline.objects.filter(
            tenant_id=tenant_id,
            name__icontains=pipeline_name,
            is_active=True,
        ).first()
        if new_pipeline:
            deal.pipeline = new_pipeline
            if stage_name:
                new_stage = PipelineStage.objects.filter(
                    pipeline=new_pipeline, name__icontains=stage_name).first()
                deal.stage = new_stage or PipelineStage.objects.filter(
                    pipeline=new_pipeline).order_by('order').first()
            else:
                deal.stage = PipelineStage.objects.filter(
                    pipeline=new_pipeline).order_by('order').first()
    elif stage_name and deal.pipeline:
        new_stage = PipelineStage.objects.filter(
            pipeline=deal.pipeline, name__icontains=stage_name).first()
        if new_stage:
            deal.stage = new_stage

    deal.save()

    priority_reverse = {"L": "low", "M": "medium", "H": "high"}
    return json.dumps({
        "action": "updated",
        "deal_id": str(deal.pk),
        "deal_title": deal.title,
        "deal_value": str(deal.value),
        "deal_currency": deal.currency,
        "deal_priority": priority_reverse.get(deal.priority, "medium"),
        "pipeline": deal.pipeline.name if deal.pipeline else None,
        "stage": deal.stage.name if deal.stage else None,
        "message": "Deal has been updated successfully.",
        "recommended_message_type": "text"
    })


@safe_function_tool
def search_nearby_pos(ctx: RunContextWrapper,
                      address: str = "",
                      latitude: float = 0,
                      longitude: float = 0,
                      results: int = 3):
    """
    Buscar puntos de venta o de servicio cercanos a la ubicación del usuario
    :param ctx:
    :param address: if user sent an address, city or place of reference, do not use for coordinates.
    :param latitude: latitude of the user location
    :param longitude: longitude of the user location
    :param results: quantity of results to return

    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    comfort_message.send(sender="search_product",
                         message="Buscando ubicaciones cercanas...",
                         tenant_id=session.tenant_id,
                         phone=contact.phone,
                         channel=session.channel)

    print(f"Address: {address}")
    print(f"Latitude: {latitude}, Longitude: {longitude}")

    config = TenantConfiguration.objects.get(tenant=session.tenant_id)
    maps = GoogleMapsApi(config)

    if latitude != 0 and longitude != 0:

        user_location = {"latitude": latitude, "longitude": longitude}
        print(f"User location: {user_location}")
        formatted_address = maps.get_address(latitude, longitude)

    elif address != "":
        print(f"Address: {address}")

        geocoding_result = maps.get_geocode(address.title())
        print(geocoding_result)
        if geocoding_result:
            geocoded_address = geocoding_result[0]
            formatted_address = geocoding_result[1]

            print(f"Geocoded address: {geocoded_address}")
            try:
                user_location = {
                    "latitude": geocoded_address["lat"],
                    "longitude": geocoded_address["lng"]
                }
            except (ValueError, TypeError) as e:
                logger.error("Error en search_nearby_pos %s", str(e))
                data = {
                    "address":
                    address,
                    "result":
                    "could not geocode, try searching knowledge or asking for location"
                }
                return json.dumps(data)

        else:
            data = {
                "address":
                address,
                "result":
                "could not geocode, try searching knowledge or asking for location"
            }
            return json.dumps(data)

        # distance to stores

    else:
        data = {
            "result":
            "No location or address received, ask the user for either"
        }
        return json.dumps(data)

    wp = WordPressAPIClient(config)
    stores = wp.get_wspl_stores(per_page=100)
    recommended_stores = []

    for store in stores:
        address_info = store["location_info"]

        try:
            store_latitude = float(address_info["latitude"])
            store_longitude = float(address_info["longitude"])
        except ValueError as e:
            logger.warning(f'Error con ubicación de %s', store["title"])
            continue

        distance = haversine(user_location["latitude"],
                             user_location["longitude"], store_latitude,
                             store_longitude)

        if distance < 15:
            loc = {
                "name": store["title"]["rendered"],
                "category": store["wpsl_store_category"],
                "address": address_info["address"],
                "city": address_info["city"],
                "work_hours": address_info["work_hours"],
                "phone": address_info["phone"],
                "email": address_info["email"],
                "url": address_info["url"],
                "distance": round(distance, 0)
            }

            recommended_stores.append(loc)
    sorted_places = sorted(recommended_stores,
                           key=lambda item: item["distance"])[:int(results)]
    # Sorted_places is a list from nearest to furthest

    if len(sorted_places) == 0:
        data = {"result": "no places found, try search_knowledge"}
        return json.dumps(data)
    elif len(sorted_places) == 1:
        data = {
            "recommended_message_type":
            "interactive_cta or text if has no url ",
            "user_address": formatted_address,
            "places": sorted_places,
        }
        return json.dumps(data)
    else:
        data = {
            "recommended_message_type": "interactive_list ",
            "user_address": formatted_address,
            "places": sorted_places,
        }
        return json.dumps(data)


def _approx_bounding_box(
        lat: float, lng: float,
        radius_km: float) -> Tuple[float, float, float, float]:
    """
    Calculate approximate bounding box for quick geographic filtering.
    Uses simple degree approximation (1 degree latitude ~ 111 km).
    
    :param lat: Center latitude
    :param lng: Center longitude
    :param radius_km: Radius in kilometers
    :return: Tuple of (min_lat, max_lat, min_lng, max_lng)
    """
    lat_delta = radius_km / 111.0
    cos_lat = math.cos(math.radians(lat))
    cos_lat = max(cos_lat, 0.01)
    lng_delta = radius_km / (111.0 * cos_lat)

    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)


def _get_user_location(
    address: str, latitude: float, longitude: float, maps: GoogleMapsApi
) -> Tuple[Optional[Dict[str, float]], Optional[str], Optional[str]]:
    """
    Resolve user location from coordinates or address.
    
    :param address: Address string to geocode
    :param latitude: User latitude (if provided)
    :param longitude: User longitude (if provided)
    :param maps: GoogleMapsApi instance
    :return: Tuple of (user_location dict, formatted_address, error_message)
    """
    if latitude != 0 and longitude != 0:
        user_location = {"latitude": latitude, "longitude": longitude}
        formatted_address = maps.get_address(latitude, longitude)
        return user_location, formatted_address, None

    if address:
        geocoding_result = maps.get_geocode(address.title())
        if geocoding_result:
            geocoded_address = geocoding_result[0]
            formatted_address = geocoding_result[1]
            try:
                user_location = {
                    "latitude": geocoded_address["lat"],
                    "longitude": geocoded_address["lng"]
                }
                return user_location, formatted_address, None
            except (ValueError, TypeError, KeyError):
                pass
        return None, None, "could not geocode, try searching knowledge or asking for location"

    return None, None, "No location or address received, ask the user for either"


@safe_function_tool
def search_nearby_pos_v2(ctx: RunContextWrapper,
                         address: str = "",
                         latitude: float = 0,
                         longitude: float = 0,
                         results: int = 3,
                         radius_km: float = 15.0) -> str:
    """
    Optimized version of search_nearby_pos with bounding box pre-filter and heap-based top-N.
    
    IMPROVEMENTS OVER V1:
    - Bounding box pre-filter: Eliminates stores outside radius before haversine calculation
    - Heap-based selection: O(n log k) instead of O(n log n) for top-k results
    - Configurable radius: radius_km parameter instead of hardcoded 15km
    - Type hints: Full type annotations for better IDE support
    - Extracted helpers: _get_user_location and _approx_bounding_box for reusability
    
    :param ctx: Agent context wrapper
    :param address: Address, city or place of reference (will be geocoded)
    :param latitude: Latitude of user location
    :param longitude: Longitude of user location
    :param results: Maximum number of results to return (default: 3)
    :param radius_km: Search radius in kilometers (default: 15.0)
    :return: JSON string with nearby places or error message
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    comfort_message.send(sender="search_product",
                         message="Buscando ubicaciones cercanas...",
                         tenant_id=session.tenant_id,
                         phone=contact.phone,
                         channel=session.channel)

    config = TenantConfiguration.objects.get(tenant=session.tenant_id)
    maps = GoogleMapsApi(config)

    user_location, formatted_address, error = _get_user_location(
        address, latitude, longitude, maps)

    if error:
        return json.dumps({
            "address": address if address else None,
            "result": error
        })

    user_lat = user_location["latitude"]
    user_lng = user_location["longitude"]

    min_lat, max_lat, min_lng, max_lng = _approx_bounding_box(
        user_lat, user_lng, radius_km)

    wp = WordPressAPIClient(config)
    stores = wp.get_wspl_stores(per_page=100)

    top_stores: List[Tuple[float, Dict[str, Any]]] = []
    results_int = int(results)
    total_in_radius = 0

    for store in stores:
        address_info = store.get("location_info", {})

        try:
            store_lat = float(address_info.get("latitude", 0))
            store_lng = float(address_info.get("longitude", 0))
        except (ValueError, TypeError):
            logger.warning("Error con ubicación de %s",
                           store.get("title", "unknown"))
            continue

        if not (min_lat <= store_lat <= max_lat
                and min_lng <= store_lng <= max_lng):
            continue

        distance = haversine(user_lat, user_lng, store_lat, store_lng)

        if distance > radius_km:
            continue

        total_in_radius += 1

        store_data = {
            "name": store.get("title", {}).get("rendered", ""),
            "category": store.get("wpsl_store_category", []),
            "address": address_info.get("address", ""),
            "city": address_info.get("city", ""),
            "work_hours": address_info.get("work_hours", ""),
            "phone": address_info.get("phone", ""),
            "email": address_info.get("email", ""),
            "url": address_info.get("url", ""),
            "distance": round(distance, 1)
        }

        if len(top_stores) < results_int:
            heapq.heappush(top_stores, (-distance, store_data))
        elif distance < -top_stores[0][0]:
            heapq.heapreplace(top_stores, (-distance, store_data))

    sorted_places = [
        store for _, store in sorted(top_stores, key=lambda x: -x[0])
    ]

    if not sorted_places:
        return json.dumps({"result": "no places found, try search_knowledge"})

    message_type = "interactive_cta or text if has no url" if len(
        sorted_places) == 1 else "interactive_list"

    return json.dumps({
        "recommended_message_type": message_type,
        "user_address": formatted_address,
        "places": sorted_places,
        "search_radius_km": radius_km,
        "total_in_radius": total_in_radius,
        "showing": len(sorted_places)
    })


def _get_vertex_coords(vertex: Dict[str, Any]) -> Tuple[float, float]:
    lat = vertex.get("lat") or vertex.get("latitude")
    lng = vertex.get("lng") or vertex.get("longitude")

    if lat is None or lng is None:
        raise ValueError(f"Invalid polygon vertex: {vertex}")

    return float(lat), float(lng)


def _normalize_polygon(polygon: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Google Maps polygons are NOT closed.
    This ensures last point == first point.
    """
    if not polygon or len(polygon) < 3:
        return []

    first = polygon[0]
    last = polygon[-1]

    if first.get("lat") != last.get("lat") or first.get("lng") != last.get(
            "lng"):
        polygon = polygon + [first]

    return polygon


def _point_in_polygon(lat: float, lng: float,
                      polygon: List[Dict[str, Any]]) -> bool:
    polygon = _normalize_polygon(polygon)
    if not polygon:
        return False

    x = lng  # longitude
    y = lat  # latitude

    inside = False
    j = len(polygon) - 1

    for i in range(len(polygon)):
        yi, xi = _get_vertex_coords(polygon[i])
        yj, xj = _get_vertex_coords(polygon[j])

        # skip horizontal edges (prevents division by zero)
        if yi == yj:
            j = i
            continue

        if (yi > y) != (yj > y):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_intersect:
                inside = not inside

        j = i

    return inside


def _is_service_available_now(business_hours: List[Dict[str, Any]],
                              tz_name: str = "America/Montevideo") -> bool:

    if not business_hours:
        return False

    tz = pytz.timezone(tz_name)
    now = timezone.now().astimezone(tz)
    today = now.strftime("%A").lower()
    now_t = now.time()

    valid_entries = [
        e for e in business_hours if e.get("day", "").lower() == today
        and e.get("enabled", False) and e.get("open") and e.get("close")
    ]

    if not valid_entries:
        return False

    for entry in valid_entries:
        try:
            open_h, open_m = map(int, entry["open"].split(":"))
            close_h, close_m = map(int, entry["close"].split(":"))
        except Exception:
            logger.warning("Invalid business_hours entry: %s", entry)
            continue

        open_t = time(open_h, open_m)
        close_t = time(close_h, close_m)

        if open_t <= close_t:
            if open_t <= now_t <= close_t:
                return True
        else:
            # overnight range (e.g. 22:00 → 02:00)
            if now_t >= open_t or now_t <= close_t:
                return True

    return False


@safe_function_tool
def check_service_availability(
    ctx: RunContextWrapper,
    address: str = "",
    latitude: float = 0,
    longitude: float = 0,
    results: int = 10,
) -> str:
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    try:
        comfort_message.send(
            sender="check_service_availability",
            message="Verificando disponibilidad de servicios...",
            tenant_id=session.tenant_id,
            phone=contact.phone,
            channel=session.channel,
        )
    except Exception as e:
        logger.error(str(e))
        
    config = TenantConfiguration.objects.get(tenant=session.tenant_id)
    maps = GoogleMapsApi(config)

    user_location, formatted_address, error = _get_user_location(
        address, latitude, longitude, maps)

    if error:
        logger.error(error)
        return json.dumps({"result": error})

    services = KnowledgeItem.objects.filter(
        tenant=session.tenant,
        type="service-template",
        visibility=VisibilityChoices.PUBLIC,
    )

    available = []
    unavailable = []

    for service in services:
        data = service.data or {}
        area = data.get("service_area") or data.get("coverage_area") or {}
        polygon = area.get("polygon", [])
        business_hours = data.get("business_hours", [])

        try:
            in_area = _point_in_polygon(
                user_location["latitude"],
                user_location["longitude"],
                polygon,
            )
        except Exception as e:
            logger.error("Polygon error on %s: %s", service.pk, e)
            in_area = False

        is_open = _is_service_available_now(business_hours)

        info = {
            "id": str(service.pk),
            "title": service.title,
            "description": service.description,
            "category": service.category,
            "url": service.url,
            "in_service_area": in_area,
            "is_currently_open": is_open,
        }

        if in_area and is_open:
            available.append(info)

        elif in_area:
            info["reason"] = "outside_business_hours"
            unavailable.append(info)

    # ✅ NORMAL CASE
    if available or unavailable:
        return json.dumps(
            {
                "user_address": formatted_address,
                "user_location": user_location,
                "available_services": available[:int(results)],
                "services_outside_hours": unavailable[:int(results)],
                "total_available": len(available),
                "total_in_area": len(available) + len(unavailable),
            },
            cls=DjangoJSONEncoder)

    # 🔁 FALLBACK: nearby POS
    logger.info(
        "No polygon services matched → fallback to search_nearby_pos_v2")
    return json.dumps({"result": "no services available in user location"})


@safe_function_tool
def get_tips(ctx: RunContextWrapper, search_term: str):
    """
    Buscar la base de conocimiento para ofrecer soluciones y consejos
    :param ctx:
    :param search_term:

    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    config = TenantConfiguration.objects.get(tenant=session.tenant_id)
    wp = WordPressAPIClient(config)
    posts = wp.get_posts(per_page=100)
    tips = []
    for post in posts:
        item = {
            "title": post["title"],
            "url": post["link"],
            "excerpt": post["excerpt"],
        }
        tips.append(item)

    return json.dumps(tips)


@safe_function_tool
def search_knowledge(ctx: RunContextWrapper, search_term: str):
    """
    Buscar la base de conocimientos para responder a cualquier consulta
    Esta es la fuente oficial de información.
    :param ctx:
    :param search_term: Search term to look for verbatim user input

    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    print(f"Search term {search_term}")
    try:
        comfort_message.send(sender="search_product",
                         message=f"Investigando {search_term}",
                         tenant_id=session.tenant_id,
                         phone=contact.phone,
                         channel=session.channel)
    except Exception as e:
        logger.error(str(e))
        
    # Assuming you've already populated the embedding field
    mo = MoioOpenai(api_key=config.openai_api_key,
                    default_model=config.openai_default_model)
    search_term_embedding = mo.get_embedding(search_term)
    matches = KnowledgeItem.objects.filter(
        tenant=config.tenant, visibility=VisibilityChoices.PUBLIC).order_by(
            L2Distance('embedding', search_term_embedding)).annotate(
                l2_distance=L2Distance('embedding', search_term_embedding),
                cos_distance=CosineDistance(
                    'embedding',
                    search_term_embedding)).filter(l2_distance__lt=1.2)[:5]

    results = []
    for match in matches:
        if match.l2_distance < 1 or match.cos_distance < 0.5:
            item = {
                "title": match.title,
                "l2_distance": match.l2_distance,
                "cos_distance": match.cos_distance,
                "url": match.url,
                "description": match.description,
            }
            results.append(item)

    return json.dumps(results)


@safe_function_tool
def end_conversation(ctx: RunContextWrapper, conversation_summary: str):
    """
    function required every time the user ends the conversation or assistant understands conversation has ended
    :conversation_summary: A summary of the conversation, include important details like, search terms, recommendations provided, user mood. In the same language of the conversation

    """
    print('Ending Conversation')
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    session.final_summary = conversation_summary
    session.save()

    response = {"end_conversation": "true"}
    session.close()

    chatbot.events.session_ended(session)

    return json.dumps(response)


def cart_setup(ctx: RunContextWrapper):
    """
    if user requires to start an order, we must set up a cart
    """

    response = {"cart_ready": "true", "cart_id": uuid.uuid4().__str__()}
    return json.dumps(response)


def order_status(ctx: RunContextWrapper,
                 order_number: str = "",
                 customer_phone_number: str = "",
                 customer_email: str = ""):
    """
    checks for the delivery tracking status of an order
    :param ctx:
    :param order_number:
    :param customer_phone_number:
    :param customer_email:
    :return:
    """

    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    order = EcommerceOrder.objects.filter(customer_phone_number=contact.phone)
    return f"Order {order_number} is in progress"


def add_to_cart(ctx: RunContextWrapper, cart_id: str, sku: str, quantity: str):
    cart = []

    cart.append(sku)
    response = {"success": "true", "cart": cart}
    return json.dumps(response)


def customer_lookup(ctx: RunContextWrapper, phone: str):
    pass


def register_lead(ctx: RunContextWrapper, phone: str, name: str):
    pass


def create_payment_link(ctx: RunContextWrapper, amount: float):
    """
    Creates a payment link to send to the user
    :param ctx:
    :param amount:
    :return:
    """
    pass


def review_shipping_requirements(ctx: RunContextWrapper, order):
    pass


def send_order_to_fulfillment(ctx: RunContextWrapper, order):
    pass


def send_tracking_code(ctx: RunContextWrapper, order, tracking_code):
    pass


def get_satisfaction_level(ctx: RunContextWrapper, satisfaction_level: str):
    """
    use this function to store the satisfaction level of the user in a scale from 1 to 10
    :param ctx:
    :param satisfaction_level:

    """
    print(f'Satisfaction level: {satisfaction_level}')
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    session.csat = satisfaction_level
    session.save()

    response = {"saved": "true"}

    return json.dumps(response)


def register_activity(ctx: RunContextWrapper, data):
    """
    Register activity like an interactive message content received
    :param ctx:
    :param data: a json object with the activity data
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    try:
        config = TenantConfiguration.objects.get(tenant_id=session.tenant_id)
        new_activity = ActivityRecord.objects.create(tenant=config.tenant,
                                                     content=data,
                                                     source="chatbot")
        new_activity.save()
        response = {"data received": "true"}
        return json.dumps(response)

    except Exception as e:
        return json.dumps({"error": str(e)})


@safe_function_tool
def contact_update(ctx: RunContextWrapper,
                   email: str = "",
                   fullname: str = "",
                   contact_type: str = "",
                   company: str = "") -> bool:
    """
    when data from user is acquired, update the contact.
    :param company:
    :param contact_type:
    :param ctx:
    :param email: "contact email"
    :param fullname: "contact fullname"

    """
    contact = ctx.context.get("contact")
    session = ctx.context.get("session")

    update = False
    if contact.email != email and email != "":
        contact.email = email.lower()
        update = True

    if contact.fullname != fullname and fullname != "":
        contact.fullname = fullname.title()
        update = True

    if contact_type != "":
        try:
            new_contact_type = ContactType.objects.get(
                name__icontains="expert", tenant=session.tenant)

            contact.ctype = new_contact_type
            update = True
        except ContactType.DoesNotExist:
            return False

    if contact.company != company and company != "":
        update = True

    if update:
        try:
            contact.save()
            return True

        except Exception as e:
            print(e)
            return False

    return False


@safe_function_tool
def search_contact(ctx: RunContextWrapper,
                   search_term: str,
                   search_by: str = "name") -> List[dict]:
    """
    Search for contacts by name, email, or phone number.
    
    Use this to find existing contacts in the system to get their information or to verify if a contact exists.
    
    Args:
        search_term: The search query (name, email, or phone number)
        search_by: Type of search - "name", "email", "phone", or "all" (searches all fields)
    
    Returns a list of matching contacts with their details.
    """
    session = ctx.context.get("session")
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    if not search_term or not search_term.strip():
        return []

    try:
        comfort_message.send(sender="search_contact",
                             message="Buscando contacto...",
                             tenant_id=session.tenant_id,
                             phone=contact.phone,
                             channel=session.channel)
    except Exception as e:
        logger.error(str(e))

    search_term = search_term.strip()
    base_qs = Contact.objects.filter(tenant_id=session.tenant_id)

    # Determine search criteria based on search_by parameter
    if search_by.lower() == "email":
        contacts = list(base_qs.filter(email__icontains=search_term)[:50])
    elif search_by.lower() == "phone":
        contacts = list(base_qs.filter(phone__icontains=search_term)[:50])
    elif search_by.lower() == "name":
        contacts = list(base_qs.filter(fullname__icontains=search_term)[:50])
    else:  # "all" - search across all fields
        contacts = list(
            base_qs.filter(
                Q(fullname__icontains=search_term)
                | Q(email__icontains=search_term)
                | Q(phone__icontains=search_term))[:50])

    # Build results list
    results = [{
        "contact_id":
        str(c.user_id),
        "name":
        c.fullname,
        "email":
        c.email or "",
        "phone":
        c.phone or "",
        "company":
        c.company or "",
        "contact_type":
        c.ctype.name if c.ctype else None,
        "created_at":
        c.created_at.isoformat() if hasattr(c, 'created_at') else None,
    } for c in contacts]

    return results


@safe_function_tool
def create_or_update_contact(ctx: RunContextWrapper,
                              fullname: str = "",
                              contact_id: str = "",
                              email: str = "",
                              phone: str = "",
                              company: str = "",
                              contact_type: str = "",
                              first_name: str = "",
                              last_name: str = "",
                              preferred_channel: str = "",
                              source: str = "agent"):
    """
    Create a new contact or update an existing one. Use this when managing contact information across a conversation.
    
    This tool is designed for conversations where contact details may evolve:
    - First call: Create a contact (leave contact_id empty) - returns the contact_id for future updates
    - Subsequent calls: Pass the contact_id to update the existing contact instead of creating duplicates
    
    USE THIS TOOL WHEN:
    - A new person needs to be registered in the system
    - You need to update contact information during an ongoing conversation
    - The user provides additional details (email, phone, company) after initial contact creation
    - You need to change a contact's type or preferred communication channel
    
    IMPORTANT: 
    - Always store and reuse the contact_id returned from the first call to avoid creating duplicate contacts.
    - For updates, only provide the fields you want to change - empty fields are preserved.
    - The phone number should be unique - searching for existing contacts before creating is recommended.
    
    :param fullname: Full name of the contact (required for create)
    :param contact_id: If provided, updates the existing contact. If empty, creates a new contact.
    :param email: Email address of the contact
    :param phone: Phone number of the contact
    :param company: Company or organization the contact belongs to
    :param contact_type: Type of contact (e.g., "Lead", "Customer", "VIP", "Partner")
    :param first_name: First name (if you prefer to set first/last separately)
    :param last_name: Last name (if you prefer to set first/last separately)
    :param preferred_channel: Preferred communication channel ("email", "whatsapp", "sms", "call")
    :param source: Source of the contact creation (default: "agent")
    
    Returns JSON with action performed (created/updated), contact_id, and contact details.
    """
    session = ctx.context.get("session")
    config = ctx.context.get("config")

    tenant_id = session.tenant_id

    existing_contact = None
    if contact_id:
        try:
            existing_contact = Contact.objects.get(user_id=contact_id, tenant_id=tenant_id)
        except Contact.DoesNotExist:
            pass

    if existing_contact:
        if fullname:
            existing_contact.fullname = fullname
        if email:
            existing_contact.email = email
        if phone:
            existing_contact.phone = phone
        if company:
            existing_contact.company = company
        if first_name:
            existing_contact.first_name = first_name
        if last_name:
            existing_contact.last_name = last_name
        if preferred_channel:
            existing_contact.preferred_channel = preferred_channel
        if contact_type:
            ctype = ContactType.objects.filter(
                tenant_id=tenant_id,
                name__iexact=contact_type
            ).first()
            if ctype:
                existing_contact.ctype = ctype
        existing_contact.save()

        response = {
            "action": "updated",
            "contact_id": str(existing_contact.user_id),
            "fullname": existing_contact.fullname or "",
            "email": existing_contact.email or "",
            "phone": existing_contact.phone or "",
            "company": existing_contact.company or "",
            "contact_type": existing_contact.ctype.name if existing_contact.ctype else None,
            "first_name": existing_contact.first_name or "",
            "last_name": existing_contact.last_name or "",
            "preferred_channel": existing_contact.preferred_channel or "",
            "message": "Contact has been updated successfully."
        }
    else:
        computed_fullname = fullname
        if not computed_fullname and (first_name or last_name):
            computed_fullname = f"{first_name} {last_name}".strip()

        if not computed_fullname:
            return json.dumps({
                "action": "error",
                "message": "A fullname or first_name/last_name is required to create a contact."
            })

        ctype = None
        if contact_type:
            ctype = ContactType.objects.filter(
                tenant_id=tenant_id,
                name__iexact=contact_type
            ).first()

        new_contact = Contact.objects.create(
            tenant_id=tenant_id,
            fullname=computed_fullname,
            email=email or "",
            phone=phone or "",
            company=company or "",
            first_name=first_name or "",
            last_name=last_name or "",
            preferred_channel=preferred_channel or "",
            source=source,
            ctype=ctype
        )

        response = {
            "action": "created",
            "contact_id": str(new_contact.user_id),
            "fullname": new_contact.fullname or "",
            "email": new_contact.email or "",
            "phone": new_contact.phone or "",
            "company": new_contact.company or "",
            "contact_type": new_contact.ctype.name if new_contact.ctype else None,
            "first_name": new_contact.first_name or "",
            "last_name": new_contact.last_name or "",
            "preferred_channel": new_contact.preferred_channel or "",
            "message": "Contact has been created successfully."
        }

    return json.dumps(response)


@safe_function_tool
def create_contact(ctx: RunContextWrapper,
                   fullname: str,
                   email: str = "",
                   phone: str = "",
                   company: str = "",
                   contact_type: str = "",
                   first_name: str = "",
                   last_name: str = "",
                   preferred_channel: str = "",
                   source: str = "agent"):
    """
    Create a new contact (non-dual helper; does NOT update).

    :param fullname: Full name (required). If empty, first_name/last_name will be used.
    :param email: Email address (optional)
    :param phone: Phone number (optional)
    :param company: Company/organization (optional)
    :param contact_type: ContactType name (optional)
    :param first_name: First name (optional)
    :param last_name: Last name (optional)
    :param preferred_channel: Preferred communication channel (optional)
    :param source: Source label (default: "agent")

    Returns JSON with action performed and contact details.
    """
    session = ctx.context.get("session")
    tenant_id = session.tenant_id

    computed_fullname = (fullname or "").strip()
    if not computed_fullname and (first_name or last_name):
        computed_fullname = f"{first_name} {last_name}".strip()

    if not computed_fullname:
        return json.dumps({
            "action": "error",
            "message": "A fullname or first_name/last_name is required to create a contact."
        })

    ctype = None
    if contact_type:
        ctype = ContactType.objects.filter(
            tenant_id=tenant_id,
            name__iexact=contact_type,
        ).first()

    new_contact = Contact.objects.create(
        tenant_id=tenant_id,
        fullname=computed_fullname,
        email=email or "",
        phone=phone or "",
        company=company or "",
        first_name=first_name or "",
        last_name=last_name or "",
        preferred_channel=preferred_channel or "",
        source=source,
        ctype=ctype,
    )

    return json.dumps({
        "action": "created",
        "contact_id": str(new_contact.user_id),
        "fullname": new_contact.fullname or "",
        "email": new_contact.email or "",
        "phone": new_contact.phone or "",
        "company": new_contact.company or "",
        "contact_type": new_contact.ctype.name if new_contact.ctype else None,
        "first_name": new_contact.first_name or "",
        "last_name": new_contact.last_name or "",
        "preferred_channel": new_contact.preferred_channel or "",
        "message": "Contact has been created successfully."
    })


@safe_function_tool
def update_contact(ctx: RunContextWrapper,
                   contact_id: str,
                   fullname: str = "",
                   email: str = "",
                   phone: str = "",
                   company: str = "",
                   contact_type: str = "",
                   first_name: str = "",
                   last_name: str = "",
                   preferred_channel: str = ""):
    """
    Update an existing contact (non-dual helper; does NOT create).

    :param contact_id: Existing contact id (required)
    :param fullname: Full name (optional)
    :param email: Email address (optional)
    :param phone: Phone number (optional)
    :param company: Company/organization (optional)
    :param contact_type: ContactType name (optional)
    :param first_name: First name (optional)
    :param last_name: Last name (optional)
    :param preferred_channel: Preferred communication channel (optional)

    Returns JSON with action performed and contact details.
    """
    session = ctx.context.get("session")
    tenant_id = session.tenant_id

    try:
        existing_contact = Contact.objects.get(user_id=contact_id,
                                               tenant_id=tenant_id)
    except Contact.DoesNotExist:
        return json.dumps({
            "action": "error",
            "contact_id": str(contact_id),
            "message": "Contact not found."
        })

    if fullname:
        existing_contact.fullname = fullname
    if email:
        existing_contact.email = email
    if phone:
        existing_contact.phone = phone
    if company:
        existing_contact.company = company
    if first_name:
        existing_contact.first_name = first_name
    if last_name:
        existing_contact.last_name = last_name
    if preferred_channel:
        existing_contact.preferred_channel = preferred_channel
    if contact_type:
        ctype = ContactType.objects.filter(
            tenant_id=tenant_id,
            name__iexact=contact_type,
        ).first()
        if ctype:
            existing_contact.ctype = ctype

    existing_contact.save()

    return json.dumps({
        "action": "updated",
        "contact_id": str(existing_contact.user_id),
        "fullname": existing_contact.fullname or "",
        "email": existing_contact.email or "",
        "phone": existing_contact.phone or "",
        "company": existing_contact.company or "",
        "contact_type": existing_contact.ctype.name if existing_contact.ctype else None,
        "first_name": existing_contact.first_name or "",
        "last_name": existing_contact.last_name or "",
        "preferred_channel": existing_contact.preferred_channel or "",
        "message": "Contact has been updated successfully."
    })


class ProductItem(BaseModel):
    sku: str = Field(..., min_length=1, examples=["ABC-123"])
    quantity: int = Field(..., gt=0, description="Units requested")
    price: Optional[float] = Field(
        default=None, gt=0, description="Unit price (omit when unknown)")


class Products(RootModel[List[ProductItem]]):
    """A JSON array of product objects."""
    pass


def create_order(ctx: RunContextWrapper, first_name: str, last_name: str,
                 phone: str, address: str, city: str, postal_code: str,
                 email: str, products: Products):
    """
    Takes data from the conversation and creates a new order
    :param : first_name: first name
    :param : last_name: last name
    :param : phone: phone number
    :param : address: street address
    :param : city: city name
    :param : email: email address
    :param : postal_code: postal code
    :param : products: an array of {product_id, quantity}
    :return:
    """

    session = ctx.context.get("session")
    contact = ctx.context.get("contact")

    config = TenantConfiguration.objects.get(tenant=session.tenant_id)
    woo = WooCommerceAPI(url=config.woocommerce_site_url,
                         consumer_key=config.woocommerce_api_key,
                         consumer_secret=config.woocommerce_api_secret,
                         timeout=30)

    customer_data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "address": address,
        "city": city,
        "postcode": postal_code,
        "email": email,
    }

    order_number = woo.create_woocommerce_order(customer_data, products)

    if order_number:
        print(f"Order created successfully. Order number: {order_number}")
        data = {
            "result": "Order created successfully",
            "order_number": order_number,
        }
        return json.dumps(data)
    else:
        data = {
            "result": "Failed to create order",
            "order_number": order_number,
        }
        return json.dumps(data)


def output_formatting_instructions(ctx: RunContextWrapper, message_type: str):
    """
    Provides formatting instructions for the message
    :param ctx:
    :param message_type: type of message the assistant will compose
    :return:
    """

    instructions = """
    Generación de formato de las respuestas:
    When generating a WhatsApp message payload, follow these formatting rules to ensure compliance with the WhatsApp Cloud API:

    General Message Requirements
    "messaging_product" must always be "whatsapp".
    "recipient_type" should always be "individual" unless sending a contacts message (where it is null).
    "to" is the recipient’s phone number in E.164 format (e.g., +14155552671).
    "type" must be one of:
    "text" (text message)
    "media" (image, audio, video, or document)
    "location" (geolocation message)
    "contacts" (contact card)
    "interactive" (buttons or list messages, interactive_cta)
    Only one content type should be included per message, and other content fields must be set to null. 
    Be mindful not to exceed max length specially in titles, footers and button captions, always use succinct call to actions. 
    """

    if message_type == "audio":
        instructions = instructions + """
                        Media Messages ("type": "media")
                        Used for sending images, audio, video, and documents.
                        "media.media_type" must be one of: "image", "audio", "video", "document".
                        "media.link" must be a publicly accessible URL or a previously uploaded media ID.
                        "media.caption" is optional (max 1024 characters).
                        "media.filename" is only required for documents.
                        Allowed formats and size limits:
                        Audio: AAC, MP3, OPUS (Max 16MB)
                        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "media",
            "media": {
                "media_type": "audio",
                "link": "https://example.com/song.aac",
            }
        }
    elif message_type == "video":
        instructions = instructions + """
                        Media Messages ("type": "media")
                        Used for sending images, audio, video, and documents.
                        "media.media_type" must be one of: "image", "audio", "video", "document".
                        "media.link" must be a publicly accessible URL or a previously uploaded media ID.
                        "media.caption" is optional (max 1024 characters).
                        "media.filename" is only required for documents.
                        Allowed formats and size limits:
                        Video: MP4, 3GP (Max 16MB)
        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "media",
            "media": {
                "media_type": "video",
                "link": "https://example.com/scene.mp4",
                "caption": "Vacation"
            }
        }
    elif message_type == "image":
        instructions = instructions + """
                        Media Messages ("type": "media")
                        Used for sending images, audio, video, and documents.
                        "media.media_type" must be one of: "image", "audio", "video", "document".
                        "media.link" must be a publicly accessible URL or a previously uploaded media ID.
                        "media.caption" is optional (max 1024 characters).
                        "media.filename" is only required for documents.
                        Allowed formats and size limits:
                        Image: JPG, JPEG, PNG (Max 5MB)
        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "media",
            "media": {
                "media_type": "image",
                "link": "https://example.com/image.jpg",
                "caption": "Check this out!"
            }
        }
    elif message_type == "document":
        instructions = instructions + """
            Media Messages ("type": "media")
            Used for sending images, audio, video, and documents.
            "media.media_type" must be one of: "image", "audio", "video", "document".
            "media.link" must be a publicly accessible URL or a previously uploaded media ID.
            "media.caption" is optional (max 1024 characters).
            "media.filename" is only required for documents.
            Allowed formats and size limits:
            Document: PDF, DOC(X), XLS(X), PPT(X) (Max 100MB)
        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "media",
            "media": {
                "media_type": "document",
                "link": "https://example.com/document.pdf",
                "filename": "Monthly_Report.pdf",
                "caption": "Attached is the latest report."
            }
        }
    elif message_type == "location":
        instructions = instructions + """
        Location Messages ("type": "location")
        "latitude" and "longitude" are required (decimal format).
        "name" and "address" are optional but recommended.
        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "location",
            "location": {
                "latitude": 37.422,
                "longitude": -122.084,
                "name": "Googleplex",
                "address": "1600 Amphitheatre Parkway, Mountain View, CA"
            }
        }
    elif message_type == "contacts":
        instructions = instructions + """
        Contact Messages ("type": "contacts")
        "contacts" must be an array (max 10 contacts per message).
        Each contact must include a name and at least one phone number.
        """
        example = {
            "messaging_product":
            "whatsapp",
            "recipient_type":
            None,
            "to":
            "+14155552671",
            "type":
            "contacts",
            "contacts": [{
                "name": {
                    "formatted_name": "John Doe",
                    "first_name": "John",
                    "last_name": "Doe"
                },
                "phones": [{
                    "phone": "+1234567890",
                    "type": "CELL"
                }]
            }]
        }
    elif message_type == "interactive_list":
        instructions = instructions + """
        Interactive Messages ("type": "interactive")
        List Messages ("type": "list")
        Can have up to 10 list items under a single section.
        The "action" object contains:
        A "button" label (max 20 characters).
        A "sections" array with one section.
        Each section contains "rows", each with:
        "id" (max 200 characters).
        "title" (max 24 characters).
        "description" (max 72 characters, optional).
        "footer" (max 60 characters, optional)
        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": "Choose an option:"
                },
                "footer": {
                    "text": "Powered by WhatsApp"
                },
                "action": {
                    "button":
                    "View Options",
                    "sections": [{
                        "title":
                        "Services",
                        "rows": [{
                            "id": "option1",
                            "title": "Consultation",
                            "description": "Book a 1:1 session"
                        }, {
                            "id": "option2",
                            "title": "Support",
                            "description": "Get customer support"
                        }]
                    }]
                }
            }
        }
    elif message_type == "interactive_cta":

        instructions = instructions + """
          Message Type: Set "type": "interactive-cta-url".
            These messages contain a Call-To-Action (CTA) button that redirects users to a specific URL when clicked. They are categorized as "interactive" messages with a subtype "interactive-cta-url".
            Structure:

            "header" (optional): Short title for the message (max 60 characters).
            "body" (required): The main message content (max 1024 characters).
            "footer" (optional): Additional text at the bottom (max 60 characters).
            "action" (required): Defines the CTA button and its destination:
            "button": The text on the button (max 20 characters).
            "url": The URL that opens when the button is clicked (must be a valid URI).
            """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "message": {
                "type": "interactive-cta-url",
                "content": {
                    "header": "Special Offer!",
                    "body": "Check out our latest discounts now.",
                    "footer": "Limited time only.",
                    "action": {
                        "button": "Shop Now",
                        "url": "https://example.com/promo"
                    }
                }
            }
        }
    elif message_type == "buttons":
        instructions = instructions + """
            Reply Button Messages ("type": "button")
            Can contain up to 3 buttons.
            Each button must have:
            "id" (max 256 characters).
            "title" (max 20 characters).
            """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": "Select an option:"
                },
                "action": {
                    "buttons": [{
                        "type": "reply",
                        "reply": {
                            "id": "btn_1",
                            "title": "Order Now"
                        }
                    }, {
                        "type": "reply",
                        "reply": {
                            "id": "btn_2",
                            "title": "More Info"
                        }
                    }]
                }
            }
        }
    elif message_type == "location_request":
        instructions = instructions + """
            Location-Request Messages
            Location-Request messages ask the user to share their location by displaying a “Send Location” button
            When the user taps this button, WhatsApp opens a location picker for the user to send their GPS location. These messages are represented as an interactive message with a specific subtype:
            Type and Subtype: Use "type": "interactive" with "interactive.type": "location_request_message"
            Body: A text prompt explaining the location request (max 1024 characters, required)

            Action: Include "action": { "name": "send_location" } to trigger the location picker
            Header/Footer: Not supported for this message type (only body text is allowed).
            This format complies with WhatsApp Cloud API’s requirements for interactive location requests​, ensuring the user sees a Send Location button.
            """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+5983212213",
            "type": "interactive",
            "interactive": {
                "type": "location_request_message",
                "body": {
                    "text": "Please share your location with us."
                },
                "action": {
                    "name": "send_location"
                }
            }
        }
    elif message_type == "interactive_flow":
        instructions = instructions + """
                        Interactive-Flow Message
                        Interactive-Flow messages are a special type of messages used only when a flow_id is provided.

                        Type and Subtype: Use "type": "interactive" with "interactive.type": "flow

                        Header/Body/Footer: You can include optional text in "header", "body", and "footer" to describe the flow (e.g., a title or instructions)​.
                        Within "parameters", provide the identifiers and settings for the flow:

                        flow_id: The ID of the flow
                        flow_message_version: Version of the flow format (e.g., "3" for current version)​.
                        flow_token: A token or key issued for your flow (from WhatsApp) to authorize launching it​.
                        flow_cta: The text for the Call-To-Action button that opens the flow (e.g., "Book now"). 
                        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+59821332123",
            "type": "interactive",
            "interactive": {
                "type": "flow",
                "header": {
                    "type": "text",
                    "text": "Example Flow"
                },
                "body": {
                    "text": "Please follow the steps in this flow."
                },
                "footer": {
                    "text": "Thank you!"
                },
                "action": {
                    "name": "flow",
                    "parameters": {
                        "flow_id": "31231234213123",
                        "flow_message_version": "3",
                        "flow_token": "unused",
                        "flow_cta": "Start Now",
                        "flow_action": "navigate",
                        "flow_action_payload": {
                            "screen": "FIRST_ENTRY_SCREEN",
                            "data": {}
                        }
                    }
                }
            }
        }
    elif message_type == "single_product_message":
        instructions = instructions + """
                        Single-Product Messages
                        Single-Product messages showcase one specific product from a WhatsApp Business product catalog. They appear with the product’s image, title, price, and a button to view more details. The schema for these messages uses an interactive object of type “product”:
                        Type and Subtype: "type": "interactive" with "interactive.type": "product"
                        Body/Footer: You can provide a description or promotional text in the "body.text", and optional additional info in "footer.text"

                        Note: Header is not allowed for product messages
                        Action: The "action" object must specify the product to display:
                        "catalog_id": The unique ID of the Facebook catalog linked to your WhatsApp Business account that contains the product
                        "product_retailer_id": The identifier of the specific product in the catalog (this is the product’s SKU or ID in your catalog)
                        This will send a message featuring the product identified by <PRODUCT_ID> from the given catalog. 
                        The user will see the product’s details and can tap it to view more. According to WhatsApp API rules, a header cannot be set for this type of message, so we use body text (and footer if needed) for any captions or descriptions.
                        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "<PHONE_NUMBER>",
            "type": "interactive",
            "interactive": {
                "type": "product",
                "body": {
                    "text": "Check out our featured product of the day!"
                },
                "footer": {
                    "text": "Limited time offer."
                },
                "action": {
                    "catalog_id": "<CATALOG_ID>",
                    "product_retailer_id": "<PRODUCT_ID>"
                }
            }
        }
    elif message_type == "multi_product_message":
        instructions = """ 
                        Multi-Product messages allow you to showcase multiple products (up to 30) from your catalog in one message
                        Users can scroll through a list or carousel of products and add them to their cart within WhatsApp. The schema uses an interactive object of type “product_list”:
                        Type and Subtype: "type": "interactive" with "interactive.type": "product_list"

                        Header/Body/Footer: Provide text for each section of the message:
                        "header.text" – e.g., a title like “Our New Arrivals” (header is typically required for multi-product messages)
                        "body.text" – introduction or details about the list, e.g., “Browse our catalog:”.
                        "footer.text" – optional footer note, e.g., “Tap a product for details.”.
                        Action: Use "action": { "catalog_id": "<CATALOG_ID>", "sections": [ ... ] } to list products. Products are grouped into sections (each section can have a title and a list of items):
                        Each section in "sections" has a "title" (category or group name) and an array of "product_items".
                        Each "product_items" entry is an object with a "product_retailer_id" for a product in the catalog

                        You can include up to 30 product items in total, split across at most 10 sections (e.g., 3 sections of 10 products each)
                        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "<PHONE_NUMBER>",
            "type": "interactive",
            "interactive": {
                "type": "product_list",
                "header": {
                    "type": "text",
                    "text": "Our New Arrivals"
                },
                "body": {
                    "text": "Here are some products you might like:"
                },
                "footer": {
                    "text": "Tap a product to view details or purchase."
                },
                "action": {
                    "catalog_id":
                    "<CATALOG_ID>",
                    "sections": [{
                        "title":
                        "Featured",
                        "product_items": [{
                            "product_retailer_id":
                            "<PRODUCT_ID_1>"
                        }, {
                            "product_retailer_id":
                            "<PRODUCT_ID_2>"
                        }]
                    }]
                }
            }
        }
    else:
        instructions = instructions + """
        Text Messages ("type": "text")
        "text.body" is required (max 4096 characters).
        "text.preview_url" should be "true" if the message contains a URL and should show a preview.
        """
        example = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "+14155552671",
            "type": "text",
            "text": {
                "body": "Hello, check this out: https://example.com",
                "preview_url": True
            }
        }

    data = {"instructions": instructions, "example": example}

    return json.dumps(data)


"""
Named wrappers around the generic Activity service.
Each function has a tight one-liner followed by an args table so the
OpenAI function-calling agent can pick the right tool without confusion.
"""

# ───────────────────────────
# helpers
# ───────────────────────────


def _u(contact: Contact):
    """Return User instance or None (internal helper)."""
    try:
        return UserModel.objects.get(
            phone=contact.phone, tenant=contact.tenant) if contact else None
    except UserModel.DoesNotExist:
        return None


def _iso_normalise(iso_str: str):
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = timezone.make_aware(dt, timezone=pytz.UTC)
    return dt.astimezone(pytz.UTC).isoformat()


# ───────────────────────────
# CREATE FUNCTIONS
# ───────────────────────────


@safe_function_tool
def create_task(
    ctx: RunContextWrapper,
    title: str,
    description: str,
    due_date: str,
    priority: int = 3,
    status: str = "open",
):
    """
    Create a **task**.

    Args:
        ctx:
        title (str): Short summary.
        description (str): Detailed body.
        due_date (str, ISO 8601): Deadline.
        priority (int, 1-5): Lower = less important.
        status (str): “open” | “in_progress” | “done”.
        user_id (str, optional): Owner of the task.
    """
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    content = {
        "description": description,
        "due_date": _iso_normalise(due_date),
        "priority": priority,
        "status": status,
    }

    activity = create_activity("task",
                               title=title,
                               content=content,
                               tenant=config.tenant,
                               user=_u(contact))

    if activity:
        return json.dumps({
            "task_created": "true",
            "activity_id": str(activity.pk),
            "title": title,
            "due_date": content["due_date"],
            "priority": priority,
            "status": status
        })
    else:
        return json.dumps({"task_created": "false"})


@safe_function_tool
def create_note(ctx: RunContextWrapper,
                title: str,
                body: str,
                tags: list[str] | None = None,
                user_id: str | None = None):
    """
    Create a **note**.

    Args:
        ctx:
        title (str): Short headline.
        body (str): Free-text content.
        tags (list[str], optional): Tags for searching.
        user_id (str, optional): Author.
    """
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")
    content = {"body": body, "tags": tags or []}

    activity = create_activity("note",
                               title,
                               content,
                               tenant=config.tenant,
                               user=_u(contact))

    if activity:
        return json.dumps({
            "note_created": "true",
            "activity_id": str(activity.pk),
            "title": title,
            "body": body,
            "tags": tags or []
        })
    else:
        return json.dumps({"note_created": "false"})


@safe_function_tool
def create_idea(ctx: RunContextWrapper,
                title: str,
                body: str,
                impact: int,
                tags: list[str] | None = None,
                user_id: str | None = None):
    """
    Log an **idea**.

    Args:
        ctx:
        title (str): Idea headline.
        body (str): Description.
        impact (int, 1-10): Perceived impact score.
        tags (list[str], optional): Keywords.
        user_id (str, optional): Submitter.
    """
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")
    content = {"body": body, "impact": impact, "tags": tags or []}

    activity = create_activity("idea",
                               title,
                               content,
                               tenant=config.tenant,
                               user=_u(contact))

    if activity:
        return json.dumps({
            "idea_created": "true",
            "activity_id": str(activity.pk),
            "title": title,
            "body": body,
            "impact": impact,
            "tags": tags or []
        })
    else:
        return json.dumps({"idea_created": "false"})


@safe_function_tool
def create_event(ctx: RunContextWrapper,
                 title: str,
                 start: str,
                 end: str,
                 location: str | None = None,
                 participants: list[str] | None = None,
                 user_id: str | None = None):
    """
    Create an **event**.

    Args:
        ctx:
        title (str): Event name.
        start (str, ISO 8601): Start datetime.
        end (str, ISO 8601): End datetime.
        location (str, optional): Place / link.
        participants (list[str], optional): People IDs or names.
        user_id (str, optional): Organizer.
    """
    contact = ctx.context.get("contact")
    config = ctx.context.get("config")

    content = {
        "start": _iso_normalise(start),
        "end": _iso_normalise(end),
        "location": location,
        "participants": participants or [],
    }

    activity = create_activity("event",
                               title,
                               content,
                               tenant=config.tenant,
                               user=_u(contact))

    if activity:
        return json.dumps({
            "event_created": "true",
            "activity_id": str(activity.pk),
            "title": title,
            "start": content["start"],
            "end": content["end"],
            "location": location,
            "participants": participants or []
        })
    else:
        return json.dumps({"event_created": "false"})


# ───────────────────────────
# RETRIEVAL FUNCTIONS
# ───────────────────────────


@safe_function_tool
def list_tasks(ctx: RunContextWrapper,
               status: str | None = None,
               due_before: str | None = None,
               due_after: str | None = None,
               priority_min: int | None = None,
               priority_max: int | None = None,
               search: str | None = None,
               limit: int | None = 50):
    """
    Fetch **tasks** with optional filters.

    Args:
        user_id (str, optional): Restrict to user.
        status (str, optional): Filter by status.
        due_before / due_after (ISO 8601): Due-date range.
        priority_min / priority_max (int): Priority range.
        search (str, optional): ILIKE on title / body.
        limit (int): Max results.
    """
    filters = {}
    if status: filters["content.status"] = status
    if due_before: filters["content.due_date__lte"] = due_before
    if due_after: filters["content.due_date__gte"] = due_after
    if priority_min: filters["content.priority__gte"] = priority_min
    if priority_max: filters["content.priority__lte"] = priority_max

    contact = ctx.context.get("contact")

    activities = query_activities(kind="task",
                                  user=_u(contact),
                                  search=search,
                                  filters=filters,
                                  order=["content__due_date"],
                                  limit=limit)

    results = [{
        "activity_id": str(a.pk),
        "title": a.title,
        "description": a.content.get("description", ""),
        "due_date": a.content.get("due_date"),
        "priority": a.content.get("priority"),
        "status": a.content.get("status"),
        "created_at": a.created_at.isoformat() if a.created_at else None
    } for a in activities]

    return json.dumps({"tasks": results, "count": len(results)})


@safe_function_tool
def search_notes(ctx: RunContextWrapper,
                 tag: str | None = None,
                 search: str | None = None,
                 limit: int | None = 50):
    """
    Free-text search inside **notes**.

    Args:
        user_id (str, optional): Author filter.
        tag (str, optional): Must have tag.
        search (str, optional): Text search.
        limit (int): Max results.
    """
    filters = {}
    if tag:
        filters["content.tags__contains"] = [tag]

    contact = ctx.context.get("contact")

    activities = query_activities("note", _u(contact), search, filters, limit=limit)

    results = [{
        "activity_id": str(a.pk),
        "title": a.title,
        "body": a.content.get("body", ""),
        "tags": a.content.get("tags", []),
        "created_at": a.created_at.isoformat() if a.created_at else None
    } for a in activities]

    return json.dumps({"notes": results, "count": len(results)})


@safe_function_tool
def list_ideas(ctx: RunContextWrapper,
               min_impact: int | None = None,
               tag: str | None = None,
               search: str | None = None,
               limit: int | None = 50):
    """
    List **ideas**, highest impact first.

    Args:
        user_id (str, optional): Creator.
        min_impact (int, optional): Impact ≥ value.
        tag (str, optional): Must contain tag.
        search (str, optional): Text search.
        limit (int): Max results.
    """
    filters = {}
    if min_impact: filters["content.impact__gte"] = min_impact
    if tag: filters["content.tags__contains"] = [tag]

    contact = ctx.context.get("contact")
    activities = query_activities("idea",
                                  _u(contact),
                                  search,
                                  filters,
                                  order=["-content__impact", "-created_at"],
                                  limit=limit)

    results = [{
        "activity_id": str(a.pk),
        "title": a.title,
        "body": a.content.get("body", ""),
        "impact": a.content.get("impact"),
        "tags": a.content.get("tags", []),
        "created_at": a.created_at.isoformat() if a.created_at else None
    } for a in activities]

    return json.dumps({"ideas": results, "count": len(results)})


@safe_function_tool
def upcoming_events(ctx: RunContextWrapper,
                    start_after: str | None = None,
                    limit: int | None = 50):
    """
    Return **events** that haven’t ended yet.

    Args:
        user_id (str, optional): Organizer filter.
        start_after (ISO 8601, optional): Default = now().
        limit (int): Max results.
    """
    start_after = start_after or timezone.now().isoformat()
    filters = {"content.end__gte": start_after}

    contact = ctx.context.get("contact")

    activities = query_activities("event",
                                  _u(contact),
                                  filters=filters,
                                  order=["content__start"],
                                  limit=limit)

    results = [{
        "activity_id": str(a.pk),
        "title": a.title,
        "start": a.content.get("start"),
        "end": a.content.get("end"),
        "location": a.content.get("location"),
        "participants": a.content.get("participants", []),
        "created_at": a.created_at.isoformat() if a.created_at else None
    } for a in activities]

    return json.dumps({"events": results, "count": len(results)})
