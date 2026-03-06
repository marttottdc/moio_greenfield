import json

import pandas as pd
from celery import shared_task
from celery.result import AsyncResult
from pydantic import BaseModel, create_model

from campaigns.models import Campaign, Channel, Kind, CampaignDataStaging
from django.conf import settings

from chatbot.lib.whatsapp_client_api import replace_template_placeholders, compose_template_based_message
from portal.models import TenantConfiguration
from typing import Any, Dict, List, Literal, Optional
from openai import OpenAI, OpenAIError

import json

import phonenumbers
from phonenumbers import PhoneNumberFormat

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

import logging

logger = logging.getLogger(__name__)

def is_url(s: str) -> bool:
    validate = URLValidator()
    try:
        validate(s)
        return True
    except ValidationError:
        return False


def is_international_format(phone: str) -> bool:
    if not phone.startswith("+"):
        return False

    try:
        parsed = phonenumbers.parse(phone, None)  # None = don't assume region
        return phonenumbers.is_possible_number(parsed) and phonenumbers.is_valid_number(parsed)
    except phonenumbers.NumberParseException:
        return False


def fix_phone_number(phone: str, region: str) -> str | None:
    try:
        parsed = phonenumbers.parse(phone, region)
        if phonenumbers.is_possible_number(parsed) and phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
        return None

    except phonenumbers.NumberParseException as e:
        logger.error(e)
        return None


def sanitize_key(key: str) -> str:
    """Make dict keys valid Python identifiers for Pydantic fields."""
    return key.replace("-", "_").replace(" ", "_")


def make_dynamic_model(name: str, payload: dict) -> BaseModel:
    """
    Create a Pydantic model from a nested dict with key sanitization.
    """
    fields = {}
    for k, v in payload.items():
        safe_k = sanitize_key(k)

        if isinstance(v, dict):
            # Recursively build nested model
            nested_name = f"{name}_{safe_k.capitalize()}"
            nested_model = make_dynamic_model(nested_name, v)
            fields[safe_k] = (nested_model, ...)
        else:
            # Use type inference from value
            inferred_type = type(v) if v is not None else (str | None)
            fields[safe_k] = (inferred_type, v)
    return create_model(name, **fields)


def auto_correct(tenant, prompt: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto-corrects input data with Structured Outputs, handling model refusals.

    on_refusal:
      - "return_original": returns the original `data` unchanged (default)
      - "raise": raises RuntimeError(refusal_text)
      - "return_error_dict": returns {"error": refusal_text}
    """
    cfg = TenantConfiguration.objects.get(tenant=tenant)
    if not cfg.openai_integration_enabled:
        return data

    client = OpenAI(api_key=cfg.openai_api_key)

    # Strict per-payload schema

    # Anti-hallucination / refusal guidance appended to your prompt
    guardrails = (
        "\n\nIf the input cannot be validly corrected to match the schema or"
        " violates safety rules, do NOT fabricate values. Either (a) return the"
        " original object unchanged, or (b) refuse. If refusing, follow the API's"
        " refusal mechanism."
    )
    full_instructions = f"{prompt}{guardrails}"

    DynamicMessage = make_dynamic_model("DynamicMessage", data)

    try:
        resp = client.responses.parse(
            model=cfg.openai_default_model,  # e.g., "gpt-4o-2024-08-06"
            instructions=full_instructions,
            input=json.dumps(data),
            text_format=DynamicMessage,
        )
    except OpenAIError:
        # Network / auth / schema errors -> safest escape
        return data

    # ----- Refusal handling (Responses API & Chat.parse compatibility) -----

    instance = resp.output_parsed
    try:

        return instance.model_dump()
    except Exception as e:
        print(e)
        return data


def describe_configuration(tenant, prompt: str, campaign: Campaign):

    cfg = TenantConfiguration.objects.get(tenant=tenant)
    if not cfg.openai_integration_enabled:
        return None

    client = OpenAI(api_key=cfg.openai_api_key)

    # Strict per-payload schema

    full_instructions = f"{prompt}"

    try:
        resp = client.responses.create(
            model=cfg.openai_default_model,  # e.g., "gpt-4o-2024-08-06"
            instructions=full_instructions,
            input=json.dumps(campaign.config),
        )

        return resp.output_text

    except Exception as e:
        # Network / auth / schema errors -> safest escape
        return e



def set_base_config(campaign: Campaign):

    kind = campaign.kind
    channel = campaign.channel

    config = {
        "defaults": {
            "country_code": "UY",
            "save_contacts": True,
            "auto_correct": True,
        },
        "message": {},
        "data": {},
        "schedule": {}
    }

    if kind == Kind.DRIP:
        pass
    elif kind == Kind.EXPRESS:
        config["data"]["import"] = ""
        config["data"]["headers"] = []
        config["data"]["data_staging"] = None

    elif kind == Kind.PLANNED:
        pass
    elif kind == Kind.ONE_SHOT:
        pass

    if channel == Channel.EMAIL:
        config["message"]["email"] = True

    elif channel == Channel.WHATSAPP:
        config["message"]["whatsapp"] = True
        config["message"]["whatsapp_template_id"] = ""
        config["message"]["whatsapp_number"] = ""
        config["message"]["template_requirements"] = ""
        config["message"]["map"] = ""

    elif channel == Channel.SMS:
        pass

    else:
        pass

    return config


def whatsapp_message_validator(tenant, message, default_country_code):
    message_values = message.get("values", {})
    # print(message_values)
    attempt_autofix = False  # means the message could be salvageable

    for key, value in message_values.items():

        if key == "whatsapp_number":
            print("validating whatsapp number")
            possible_whatsapp_number = str(value).strip()
            if not is_international_format(possible_whatsapp_number):
                if len(possible_whatsapp_number) > 5:
                    attempt_autofix = True

                    fixed_number = fix_phone_number(possible_whatsapp_number, default_country_code)
                    print(f'fixed_number: {fixed_number}')
                    if fixed_number:


                        message_values[key] = fixed_number
                        message["valid"] = True

                    else:
                        break
            else:
                print(f"whatsapp_number: {possible_whatsapp_number} came correct")
                message["valid"] = True

        elif key.startswith("header"):
            print("validating header")

            if is_url(value):
                message["valid"] = True

                if "image" in key:
                    if is_url(value):
                        message_values["image_link"] = value

                elif "document" in key:
                    message_values["document_link"] = value

            else:
                if type(value) is str and len(value) > 0:
                    message["valid"] = True

                else:
                    attempt_autofix = True
                    break

        elif key.startswith("body"):
            print("validating body")
            if type(value) is str and len(value) > 0:
                message["valid"] = True
                new_key = key.split("_")[1]
                message_values[new_key] = value
            else:
                break

        elif key.startswith("footer"):
            print("validating footer")
            if type(value) is str and len(value) > 0:
                message["valid"] = True
                new_key = key.split("_")[1]
                message_values[new_key] = value
            else:
                message_values[key] = tenant.nombre
                new_key = key.split("_")[1]
                message_values[new_key] = value
                break

        elif key.startswith("buttons"):
            if type(value) is str and len(value) > 0:
                attempt_autofix = True

    if not message.get("valid") and attempt_autofix:

        prompt = f"""check this values for issues preventing them from 
            being sent in a whatsapp template, return the same json format just correct the values, 
            default country code for phones is {default_country_code} make sure to use the correct format including the +.
            For names, if its a person name, use the first name, if is a Company, use the full company name both title formatted"""

        try:
            auto_corrected = auto_correct(tenant, prompt, message)
            auto_corrected["valid"] = True
            return auto_corrected

        except Exception as e:
            print(e)
            return message

    return message


def whatsapp_message_generator(tenant, message_data, requirements, namespace, template):

    template_object = replace_template_placeholders(requirements, message_data)
    whatsapp_number = message_data["whatsapp_number"]

    msg = compose_template_based_message(template=template,
                                         phone=whatsapp_number,
                                         namespace=namespace,
                                         components=template_object)

    return msg


def contact_validator(tenant, message, ):
    message_values = message.get("values", {})

    attempt_autofix = False  # means the message could be salvageable
    print(f"message values: {message_values}")
    contact = {}

    for key, value in message_values.items():

        if key == "whatsapp_number":
            contact["phone"] = str(value).strip()

        if key == "contact_name":
            contact["fullname"] = str(value).strip()

    return contact


