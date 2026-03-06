import json
import re
from datetime import datetime
import pytz
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

import aiohttp
import requests
from django.core.files.storage import default_storage
from django.utils import timezone
from chatbot.models.wa_message_log import WaMessageLog
from moio_platform.lib.openai_gpt_api import whisper_to_text, image_reader
from portal.models import TenantConfiguration, PortalConfiguration
from portal.config import get_portal_configuration
from celery import shared_task
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

import re

VAR_RE = re.compile(r"{{\s*(\w+)\s*}}")


def extract_vars(text: str) -> list[str]:
    return VAR_RE.findall(text or "")

def _require(values: dict, key: str, scope: str) -> str:
    if key not in values or values[key] is None:
        raise ValueError(f"Missing template variable '{key}' in {scope}")
    val = values[key]
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val)

class WhatsappWebhook:
    def __init__(self, body):
        self.entry = body["entry"]
        self.payload = self.entry[0]["changes"][0]

    def get_type(self):
        webhook_type = self.payload["field"]
        return webhook_type

    def display_content(self):
        print("Full entry content")
        print(self.entry[0])
        print("--------------------")


class WhatsappMessage:
    def __init__(self, body):

        self.raw_message = body
        entry = body["entry"]
        self.waba_id = entry[0]["id"]
        self.waba_phone_id = entry[0]["changes"][0]["value"]["metadata"]["phone_number_id"]
        self.status = ""
        self.timestamp = None

        changes = entry[0]["changes"]
        value = changes[0]["value"]
        self.value = value
        self.msg_type = ""

        if value.get("statuses") is not None:
            self.msg_type = "status"
            self.status = value["statuses"][0]["status"]
            self.msg_id = value["statuses"][0]["id"]
            self.timestamp = int(value["statuses"][0]["timestamp"])

        elif value.get("messages") is not None:
            self.msg_type = "message"
            self.message_text = get_text_user(value["messages"][0])
            self.content_type = value["messages"][0]["type"]
            # message_bundle["msg_content"]["id"]
            self.timestamp = int(value["messages"][0]["timestamp"])

            self.profile = value["contacts"][0]

            contact = self.profile["profile"]
            self.contact_name = contact["name"]
            self.contact_number = value["messages"][0]["from"]

            context_msg_id = None
            msg_context = value["messages"][0].get("context")

            if msg_context is not None:
                context_msg_id = msg_context.get("id", None)

            self.msg_type = "message"

            self.user_message = self.message_text
            self.msg_id = value["messages"][0]["id"]
            self.context_msg_id = context_msg_id
            self.msg_content = value["messages"][0][self.content_type]

    def get_context(self):
        if self.context_msg_id:
            return self.value["messages"][0].get("context")
        else:
            return None

    def get_contact_name(self):
        if self.is_status():
            return ""

        return self.contact_name

    def get_contact_number(self):
        if self.is_status():
            return ""
        if self.contact_number.startswith("+"):
            return self.contact_number
        else:
            return f"+{self.contact_number}"

    def is_message(self):
        return self.msg_type == "message"

    def is_status(self):
        return self.msg_type == "status"

    def content_is_text(self):
        return self.content_type == "text"

    def content_is_audio(self):
        return self.content_type == 'audio'

    def content_is_video(self):
        return self.content_type == 'video'

    def content_is_document(self):
        return self.content_type == 'document'

    def content_is_image(self):
        return self.content_type == 'image'

    def content_is_button(self):
        return self.content_type == 'button'

    def content_is_order(self):
        return self.content_type == 'order'

    def content_is_contact(self):
        return self.content_type == 'contacts'

    def content_is_reaction(self):
        return self.content_type == "reaction"

    def content_is_interactive(self):
        return self.content_type == "interactive"

    def content_is_location(self):
        return self.content_type == "location"

    def get_message_text(self):

        if self.content_type == "text":

            return self.message_text

        else:
            raise ValueError(f"Unsupported content: {self.content_type}")

    def get_button_payload(self):

        payload = (
            self.value.get("messages", [{}])[0].get("button", {}).get("payload")
        )
        return payload

    def get_media_id(self):
        return self.msg_content.get("id", None)

    def get_caption(self):
        """

        :return:
        """
        return self.msg_content.get("caption", "")

    def get_emoji(self):
        return self.msg_content.get("emoji", "")

    def get_location(self):
        if self.content_is_location():
            return self.msg_content.get("interactive", "")

        return None

    def get_waba_id(self):
        return self.waba_id

    def get_waba_phone_id(self):
        return self.waba_phone_id

    def display_message(self):

        if self.is_status():
            print(f"Msg id:{self.msg_id} | Status: {self.status} ")
            self.msg_type = "status"
        else:
            print(json.dumps(self.raw_message, indent=4))

    def get_interactive_content(self):
        if self.content_is_interactive():
            print(json.dumps(self.raw_message, indent=4))

            if self.msg_content["type"] == "button_reply":
                return f'{self.msg_content["button_reply"]["id"]} - {self.msg_content["button_reply"]["title"]}'
            elif self.msg_content["type"] == "nfm_reply":
                return json.dumps(self.msg_content["nfm_reply"])

            return json.dumps(self.raw_message)

        return None

    def get_order_content(self):
        if self.content_is_order():
            return json.dumps(self.msg_content)

    def get_contact_data(self):
        if self.content_is_contact():
            return json.dumps(self.msg_content)

    def get_msg_id(self):
        return self.msg_id

    def get_context_msg_id(self):
        if self.status:
            return ""
        return self.context_msg_id

    def get_status(self):
        if self.is_status():
            return self.status
        return ""

    def get_timestamp(self):
        return self.timestamp


class WhatsappBusinessClient:

    def __init__(self, config: TenantConfiguration):

        if config.whatsapp_integration_enabled:
            portal_configuration = get_portal_configuration()

            self.whatsapp_business_account_id = config.whatsapp_business_account_id
            self.media_url = config.whatsapp_url
            self.url = config.whatsapp_url
            self.whatsapp_token = portal_configuration.fb_system_token
            self.whatsapp_phone_id = config.whatsapp_phone_id
            self.tenant = config.tenant

        else:
            raise Exception("WhatsappBusinessClient is not enabled")

    def send_message(self, data, client_name="send_message"):
        """
        Send a WhatsApp message via the Business API.
        
        Returns:
            dict: {
                "success": bool,
                "response": dict (API response),
                "status_code": int,
                "error": str (if failed)
            }
        """
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.whatsapp_token}"
            }

            api_url = f"{self.url}/{self.whatsapp_phone_id}/messages"

            print(f"Sending message")

            response = requests.post(url=api_url, data=json.dumps(data), headers=headers)
            response_json = response.json()

            msg_type = response_json.get("type", client_name)

            msg_data = {
                "tenant": self.tenant,
                "type": f"send-{msg_type}",
                "msg_content": data,
                "msg_id": "",
                "status": "",
                "user_number": "",
                "entry_id": "",
                "display_phone_number": "",
                "phone_number_id": "",
                "user_name": "",
                "user_message": "",
                "body": "",
                "context_msg_id": "",
                "recipient_id": "",
                "conversation_id": "",
                "expiration": None,
                "origin": "",
                "timestamp": timezone.now()
            }

            if response.status_code == 200:
                logger.info(f"Message sent successfully: {response_json}")

                if data.get("status", "") == "read" and response_json.get("success", ""):
                    msg_data['status'] = data.get("status", "")
                    msg_data['msg_id'] = data.get("message_id", "")

                messages = response_json.get("messages", None)
                if messages:
                    msg_data["msg_id"] = messages[0].get("id", "")
                    message_status = messages[0].get("message_status", "")
                    msg_data["status"] = messages[0].get("status", message_status)

                contacts = response_json.get("contacts", None)
                if contacts:
                    msg_data["user_number"] = contacts[0].get("input", "")

                print(f'message data:{msg_data}')
                try:
                    msg_record = WaMessageLog.objects.create(**msg_data)
                    msg_record.save()

                except Exception as e:
                    print(e)

                return {
                    "success": True,
                    "response": response_json,
                    "status_code": response.status_code,
                }
            else:
                error_msg = response_json.get("error", {}).get("message", str(response_json))
                error_code = response_json.get("error", {}).get("code", "unknown")
                logger.error(f"Error sending message: {response_json}")
                return {
                    "success": False,
                    "response": response_json,
                    "status_code": response.status_code,
                    "error": f"[{error_code}] {error_msg}",
                }

        except Exception as e:
            logger.error(str(e))
            return {
                "success": False,
                "response": None,
                "status_code": None,
                "error": str(e),
            }

    def send_outgoing_template(self, data, client_name="send_message"):
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.whatsapp_token}"
            }

            api_url = f"{self.url}/{self.whatsapp_phone_id}/messages"

            print(f"Sending message")

            response = requests.post(url=api_url, data=json.dumps(data), headers=headers)

            msg_type = response.json().get("type", client_name)

            msg_data = {
                "tenant": self.tenant,
                "type": f"send-{msg_type}",
                "msg_content": data,
                "msg_id": "",
                "status": "",
                "user_number": "",
                "entry_id": "",
                "display_phone_number": "",
                "phone_number_id": "",
                "user_name": "",
                "user_message": "",
                "body": "",
                "context_msg_id": "",
                "recipient_id": "",
                "conversation_id": "",
                "expiration": None,
                "origin": "",
                "timestamp": timezone.now()
            }

            if response.status_code == 200:
                logger.info(f"Message sent successfully: {response.json()}")
                result = response.json()

                if data.get("status", "") == "read" and result.get("success", ""):
                    msg_data['status'] = data.get("status", "")
                    msg_data['msg_id'] = data.get("message_id", "")

                messages = result.get("messages", None)
                if messages:
                    msg_data["msg_id"] = messages[0].get("id", "")
                    message_status = messages[0].get("message_status", "")
                    msg_data["status"] = messages[0].get("status", message_status)

                contacts = result.get("contacts", None)
                if contacts:
                    msg_data["user_number"] = contacts[0].get("input", "")

                print(f'message data:{msg_data}')
                try:
                    msg_record = WaMessageLog.objects.create(**msg_data)
                    msg_record.save()

                except Exception as e:
                    print(e)

                return True, result
            else:
                logger.error(f"Error sending message: {response.json()}")
                return False, response.json()

        except Exception as e:
            logger.error(str(e))
            return False

    def mark_as_read(self, msg_id):

        data = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": msg_id,
            "typing_indicator": {
                "type": "text"
            }
        }
        print(timezone.now())

        response = self.send_message(data, client_name="mark_as_read")
        return response

    def _blocklist_url(self) -> str:
        return f"{self.url}/{self.whatsapp_phone_id}/block_users"

    def _auth_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.whatsapp_token}",
        }

    def _blocklist_request(self, method: str, payload: dict, client_name: str) -> dict:
        try:
            response = requests.request(
                method=method,
                url=self._blocklist_url(),
                headers=self._auth_headers(),
                data=json.dumps(payload),
            )
            response_json = response.json()
            if response.status_code == 200:
                logger.info("%s succeeded: %s", client_name, response_json)
                return {
                    "success": True,
                    "response": response_json,
                    "status_code": response.status_code,
                }
            error_msg = response_json.get("error", {}).get("message", str(response_json))
            error_code = response_json.get("error", {}).get("code", "unknown")
            logger.error("%s failed: %s", client_name, response_json)
            return {
                "success": False,
                "response": response_json,
                "status_code": response.status_code,
                "error": f"[{error_code}] {error_msg}",
            }
        except Exception as exc:
            logger.exception("Blocklist request failed")
            return {
                "success": False,
                "response": None,
                "status_code": None,
                "error": str(exc),
            }

    def block_users(self, users: list[str]) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "block_users": [{"user": user} for user in users],
        }
        return self._blocklist_request("post", payload, client_name="block_users")

    def unblock_users(self, users: list[str]) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "block_users": [{"user": user} for user in users],
        }
        return self._blocklist_request("delete", payload, client_name="unblock_users")

    def list_blocked_users(self) -> dict:
        try:
            response = requests.get(url=self._blocklist_url(), headers=self._auth_headers())
            response_json = response.json()
            if response.status_code == 200:
                return {
                    "success": True,
                    "response": response_json,
                    "status_code": response.status_code,
                }
            error_msg = response_json.get("error", {}).get("message", str(response_json))
            error_code = response_json.get("error", {}).get("code", "unknown")
            return {
                "success": False,
                "response": response_json,
                "status_code": response.status_code,
                "error": f"[{error_code}] {error_msg}",
            }
        except Exception as exc:
            logger.exception("Failed to list blocked users")
            return {
                "success": False,
                "response": None,
                "status_code": None,
                "error": str(exc),
            }

    def process_messages(self, text, number, url=None, content_type="text"):

        if content_type == "text":
            data = compose_text_message(text, number)

        elif content_type == "image":
            data = compose_image_message(text, number, url)

        elif content_type == "audio":
            data = compose_audio_message(text, number, url)

        else:
            data = None

        if data is not None:
            if self.send_message(data):
                print("mensaje enviado")
            else:
                print("envio fallido")

    def download_message_templates(self):

        url = f'{self.url}{self.whatsapp_business_account_id}/message_templates'
        headers = {
            'Authorization': f'Bearer {self.whatsapp_token}'
        }

        try:
            iter_url = url
            templates = []
            while True:

                response = requests.get(iter_url, headers=headers)
                response.raise_for_status()

                paging = response.json().get("paging", None)
                if paging:
                    cursors = paging.get("cursors")

                    iter_url = url + f"?after={cursors['after']}"

                if len(response.json()["data"]) <= 0:
                    break

                else:
                    templates.extend(response.json()["data"])

            return templates

        except requests.exceptions.HTTPError as err:
            logger.exception(f"HTTP error occurred: {err}")

        except Exception as err:
            logger.exception(f"An error occurred: {err}")

    def template_details(self, template_id):
        url = f'{self.url}{template_id}'
        headers = {
            'Authorization': f'Bearer {self.whatsapp_token}'
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            return response.json()
        except requests.exceptions.HTTPError as err:
            print(f"HTTP error occurred: {err}")
        except Exception as err:
            print(f"An error occurred: {err}")

    def retrieve_template_namespace(self):
        url = f'{self.url}{self.whatsapp_business_account_id}/?fields=message_template_namespace'
        headers = {
            'Authorization': f'Bearer {self.whatsapp_token}'
        }
        try:
            response = requests.get(url, headers=headers)
            return response.json()["message_template_namespace"]

        except requests.exceptions.HTTPError as err:
            print(f"HTTP error occurred: {err}")

        except Exception as err:
            print(f"An error occurred: {err}")

    def download_audio(self, media_id: str):

        url = f"{self.media_url}{media_id}?phone_number_id={self.whatsapp_phone_id}"

        headers = {
            "Authorization": f"Bearer {self.whatsapp_token}"
        }

        response = requests.get(url, headers=headers)  # This request obtains the URL of the multimedia file to downlad

        content = json.loads(response.content)

        media_url = content["url"]
        mime_type = content["mime_type"]
        type, subtype = mime_type.split("/")

        media_download_response = requests.get(media_url, headers=headers)  # This request makes the download

        if media_download_response.status_code == 200:
            print(f"Download Successful {subtype} file")

            # Extract the audio data from the response content
            audio_data = media_download_response.content

            received_audio_file_name = f"media/{media_id}.{subtype}"
            # Save the file to S3

            with default_storage.open(received_audio_file_name, "wb") as f:
                f.write(audio_data)

            return received_audio_file_name

        else:
            print('Download failed')

            return None

    def download_media(self, media_id: str, return_url=False):

        url = f"{self.media_url}{media_id}?phone_number_id={self.whatsapp_phone_id}"

        headers = {
            "Authorization": f"Bearer {self.whatsapp_token}"
        }

        response = requests.get(url, headers=headers)

        content = json.loads(response.content)

        media_url = content["url"]
        mime_type = content["mime_type"]
        type, subtype = mime_type.split("/")

        media_download_response = requests.get(media_url, headers=headers)  # This request makes the download

        if media_download_response.status_code == 200:

            logger.info(f"Download Successful {subtype} file")
            # Extract the audio data from the response content
            media_data = media_download_response.content

            received_media_file_name = f"media/{media_id}.{subtype}"
            # Save the file to S3
            with default_storage.open(received_media_file_name, "wb") as f:
                f.write(media_data)

            if return_url:

                return default_storage.url(received_media_file_name)

            else:
                return received_media_file_name

        else:
            print('Download failed')

            return None

    def register_message(self, message: WhatsappMessage):
        print("Registering message")
        print(message.raw_message)
        msg_data = {
            "tenant": self.tenant,
            "msg_content": "",
            "msg_id": message.get_msg_id(),
            "status": message.get_status(),
            "user_number": message.get_contact_number(),
            "entry_id": "",
            "display_phone_number": "",
            "phone_number_id": "",
            "type": f"receive-{message.get_status()}",
            "user_name": message.get_contact_name(),
            "user_message": "",
            "body": "",
            "context_msg_id": message.get_context_msg_id(),
            "recipient_id": "",
            "conversation_id": "",
            "expiration": None,
            "origin": "",
            "timestamp": datetime.fromtimestamp(message.get_timestamp(), tz=pytz.UTC)
        }

        try:
            msg_record = WaMessageLog.objects.create(**msg_data)
            msg_record.save()

        except Exception as e:
            logger.error(e)


#  ------------------------------------------------------------------ #


def get_text_user(message):
    text = ""
    type_message = message.get("type", "")

    if type_message == "text":
        text = (message["text"])["body"]

    elif type_message == "interactive":
        interactive_object = message["interactive"]
        type_interactive = interactive_object["type"]

        if type_interactive == "button_reply":
            text = (interactive_object["button_reply"])["title"]

        elif type_interactive == "list_reply":
            text = (interactive_object["list_reply"])["title"]

        else:
            print("no message")

    else:
        print("no message")

    return text


def auto_compose(number: str, reply):
    reply_vector = []
    for reply_msg in reply:
        msg = json.loads(reply_msg)

        msg["messaging_product"] = "whatsapp"
        msg["recipient_type"] = "individual"
        msg["to"] = number
        reply_vector.append(msg)

    return reply_vector


def compose_text_message(text: str, number: str):
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "text",
        "text": {
            "preview_url": "true",
            "body": text
        }
    }

    return data


def compose_image_message(number, url, caption=""):
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "image",
        "image": {
            "link": url,
            "caption": caption
        }
    }

    return data


def compose_audio_message(text, number, url):
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "audio",
        "audio": {
            "link": url
        }
    }

    return data


def compose_video_message(text, number, url):
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "video",
        "video": {
            "link": url
        }
    }

    return data


def compose_document_message(text, number, url):
    """
    Use this when the message contains a link to a document like a doc, pdf etc.
    :param text: Short Caption
    :param number:
    :param url: link to the document
    :return:
    """

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "document",
        "document": {
            "link": url,
            "caption": text
        }
    }

    return data


def compose_location_message(text, number, latitude, longitude, nombre_lugar, address):
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "location",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "name": nombre_lugar,
            "address": address
        }
    }

    return data


def compose_multi_product_message(text, number):
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "product_list",
            "header": {
                "type": "text",
                "text": "Cabezal"
            },
            "body": {
                "text": text
            },
            "footer": {
                "text": "footer-content"
            },
            "action": {
                "catalog_id": "CATALOG_ID",
                "sections": [
                    {
                        "title": "Panes",
                        "product_items": [
                            {"product_retailer_id": "product-SKU-in-catalog"},
                            {"product_retailer_id": "product-SKU-in-catalog"},
                            ...
                        ]
                    },
                    {
                        "title": "section-title",
                        "product_items": [
                            {"product_retailer_id": "product-SKU-in-catalog"},
                            {"product_retailer_id": "product-SKU-in-catalog"},
                            ...
                        ]
                    }
                ]
            }
        }
    }
    return data


def compose_list_message(number, header, body, footer, button_caption, sections):
    """
    Compose a message containing several products.
    :param number: phone number of the user
    :param header: Header of the list, less than 20 char
    :param body: Body of the list less than 1024 char
    :param footer: Footer of the list: less than 60 char.
    :param button_caption: label for the button less than 20 char
    :param sections: is a list objects that will contain sections composed of title and a list of section_items, each section_item will contain id, title and description
    :return:
    """
    validated_sections = []
    #list of sections composing

    for item in sections:

        section_list = []

        for section_item in item.get("section_items"):
            ci = {
                "id": section_item.get("id", ""),
                "title": section_item.get("title", ""),
                "description": section_item.get("description", ""),
            }
            section_list.append(ci)
        section = {
            "title": item.get("title"),
            "rows": section_list
        }
        validated_sections.append(section)

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": header
            },
            "body": {
                "text": body
            },
            "footer": {
                "text": footer
            },
            "action": {
                "button": button_caption,
                "sections": sections
            }
        }
    }
    return data


def compose_reply_2button_message(text, number, caption_button1="si", caption_button2="no"):
    """
    Used when there are two options to display, button captions must be less than 20 char and message body less than 1024 char.
    :param text: Message text body, must be less than 1024 char
    :param number:
    :param caption_button1:  Label to appear in the button must be less than 20 char
    :param caption_button2:  Label to appear in the button must be less than 20 char
    :return:
    """

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": text
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "001",
                            "title": caption_button1
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "002",
                            "title": caption_button2
                        }
                    }
                ]
            }
        }
    }
    return data


def compose_reply_3button_message(text, number, caption_button1="si", caption_button2="no", caption_button3="no"):
    """
    Used when there are three options to display, button captions must be less than 20 char and message body less than 1024 char.
    :param text: Message text body, must be less than 1024 char
    :param number:
    :param caption_button1: Label to appear in the button must be less than 20 char
    :param caption_button2: Label to appear in the button must be less than 20 char
    :param caption_button3: Label to appear in the button must be less than 20 char
    :return:
    """
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": text
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "001",
                            "title": caption_button1
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "002",
                            "title": caption_button2
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "003",
                            "title": caption_button3
                        }
                    }
                ]
            }
        }
    }
    return data


def compose_require_location(text, number):
    """
    Used when offering to make a geosearch and getting the user location will be needed
    :param text: Message body
    :param number: phone number of the user
    :return:
    """
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "interactive",
        "to": number,
        "interactive": {
            "type": "location_request_message",
            "body": {
                "text": text
            },
            "action": {
                "name": "send_location"
            }
        }
    }
    return data


def compose_contact_message(number, contacts):
    """
    Builds a message containing a list of contact details
    :param number: phone number of the recipient
    :param contacts: is a list of contacts, whatsapp contact details.
    :return:
    """

    contact_list = []

    for contact in contacts:
        contact = {
            "addresses": [
                {
                    "street": contact.get("address", ""),
                    "city": contact.get("city", ""),
                    "state": contact.get("state", ""),
                    "zip": contact.get("zip", ""),
                    "country": contact.get("country", ""),
                    "country_code": contact.get("country_code", ""),
                    "type": contact.get("category", ""),
                }
            ],
            "birthday": contact.get("birthday", ""),
            "emails": [
                {
                    "email": contact.get("email", ""),
                    "type": contact.get("email_type", ""),
                }
            ],
            "name": {
                "formatted_name": contact.get("name", ""),
                "first_name": contact.get("first_name", ""),
                "last_name": contact.get("last_name", ""),
                "middle_name": contact.get("middle_name", ""),
                "suffix": contact.get("suffix", ""),
                "prefix": contact.get("prefix", ""),
            },
            "org": {
                "company": contact.get("company", ""),
                "department": contact.get("department", ""),
                "title": contact.get("title", ""),
            },
            "phones": [
                {
                    "phone": contact.get("phone", ""),
                    "wa_id": contact.get("wa_id", ""),
                    "type": contact.get("phone_type", ""),
                }
            ],
            "urls": [
                {
                    "url": contact.get("url", ""),
                    "type": contact.get("url_type", ""),
                }
            ]
        }
        contact_list.append(contact)

    data = {
        "messaging_product": "whatsapp",
        "to": number,
        "context": {
            "message_id": "<MSGID_OF_PREV_MSG>"
        },
        "type": "contacts",
        "contacts": contact_list
    }
    return data


def compose_reply_1button_message(text, number, caption_button1="si"):
    """
    Compose messages that could require an acknowledgement, like OK or Yes
    :param text: Body of the message must be less than 1024 char.
    :param number: Phone number of the recepient
    :param caption_button1: Label to appear in the button must be less than 20 char.
    :return:
    """
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": text
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "001",
                            "title": caption_button1
                        }
                    }
                ]
            }
        }
    }
    return data


# ========================================= TEMPLATES ======================


def iterate_templates(data):
    if isinstance(data, list):
        for d in data:
            iterate_templates(d)

    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                iterate_templates(value)
            else:
                print(f'{key}:{value}')

    print('-----------------------------------------')


def template_headers(templates):
    template_headers = []

    for template in templates["data"]:
        template_headers.append({"name": template["name"], "id": template["id"], "lang": template["language"],
                                 "category": template["category"], "status": template["status"]})
    return template_headers


def template_requirements(template, **kwargs):
    print(template)

    named = template["parameter_format"] == 'NAMED'

    if named:
        pattern = r"(\{\{.*?\}\})"

    else:
        pattern = r"{{\d}}"

    components = []

    for section in template["components"]:

        if section.get("type", "") == "HEADER":
            header_parameters = []

            if section["format"] == 'IMAGE':

                element = {
                    "type": "image",
                    "image": {
                        "link": "{{image_link}}"
                    }
                }

                header_parameters.append(element)

            elif section["format"] == 'DOCUMENT':

                element = {
                    "type": "document",
                    "document": {
                        "link": "{{document_link}}"
                    }

                }
                header_parameters.append(element)

            elif section["format"] == 'TEXT':

                for r in re.findall(pattern, section["text"]):

                    element = {
                        "type": "text",
                        "text": "{{header_text}}"
                    }
                    if named:
                        element["parameter_name"] = r.replace("{{", "").replace("}}", "")

                    header_parameters.append(element)

            header_components = {
                "type": "header",
                "parameters": header_parameters
            }

            components.append(header_components)

        if section["type"] == "BODY":

            body_parameters = []

            for r in re.findall(pattern, section["text"]):
                print(f"found r: {r}")
                element = {
                    "type": "text",
                    "text": r
                }
                if named:
                    element["parameter_name"] = r.replace("{{", "").replace("}}", "")

                body_parameters.append(element)

            body_components = {
                "type": "body",
                "parameters": body_parameters
            }
            components.append(body_components)

        if section["type"] == "FOOTER":
            pass

        elif section["type"] == "BUTTONS":
            button_parameters = []

            for button in section["buttons"]:
                if button["type"] == "PHONE_NUMBER":
                    pass

                elif button["type"] == "URL":
                    pattern = r"{{\d}}"

                    parameters = []
                    for r in re.findall(pattern, button["url"]):
                        print(f'encontrado {r}')
                        button_var = {
                            "type": "text",
                            "text": r
                        }
                        parameters.append(button_var)
                    if len(parameters) > 0:
                        element = {
                            "type": "button",
                            "sub_type": "url",
                            "index": 0,
                            "parameters": parameters

                        }
                        components.append(element)

                elif button["type"] == "QUICK_REPLY":
                    pass
                elif button["type"] == "OTP":
                    pass
                elif button["type"] == "MPM":
                    pass
                elif button["type"] == "CATALOG":
                    pass
                elif button["type"] == "FLOW":
                    element = {
                        "type": "button",
                        "sub_type": "flow",
                        "index": "0",
                        "parameters": [
                            {
                                "type": "action",
                                "action": {
                                    "flow_token": "unused",
                                },
                            }
                        ]
                    }
                    components.append(element)

                elif button["type"] == "VOICE_CALL":
                    pass
                elif button["type"] == "APP":
                    pass

            button_components = {
                "type": "button",
                "parameters": button_parameters
            }

    return components


def build_var_list(reqs):
    vars_list = []
    for req in reqs:

        if req.get("whatsapp_number"):
            whatsapp_number = input("Input Whatsapp Number: ")
            element = {"whatsapp_number": whatsapp_number}
            vars_list.append(element)

        if req.get("header"):
            link = input("Input media link: ")
            element = {f"{req.get('header')}": link}
            print(element)
            vars_list.append(element)

        if req.get("text_body"):
            text_body = req["text_body"]
            text_params = []
            for text_var in text_body:
                text_element = {
                    "type": "text",
                    "text": input(f"Input value for text var {text_var['text']} ")
                }
                text_params.append(text_element)
            text_body_variables = {"text_body_variables": text_params}
            vars_list.append(text_body_variables)

        if req.get("button_vars"):
            button_url = input("Input button URL ending: ")
            element = {"button_vars": button_url}
            vars_list.append(element)

    return vars_list


def compose_media_template_message(template, template_vars):
    template_components = []
    body_parameters = []
    buttons_parameters = {}

    for element in template_vars:

        if element.get("whatsapp_number"):
            whatsapp_number = element["whatsapp_number"]

        if element.get("image_URL", ""):
            header_parameters = [
                {
                    "type": "image",
                    "image": {
                        "link": element.get("image_URL", "")
                    }
                }
            ]

        elif element.get("document_URL", ""):
            header_parameters = [
                {
                    "type": "document",
                    "document": {
                        "link": element.get("document_URL", "")
                    }
                }
            ]

        elif element.get("text"):
            header_parameters = [
                {
                    "type": "text",
                    "text": element.get("text")

                }
            ]

        for text_var in element.get("text_body_variables", ""):
            body_parameters.append({"type": "text", "text": text_var})

        for currency_var in element.get("currency_body_variables", ""):
            body_parameters.append(
                {
                    "type": "currency",
                    "currency": {
                        "fallback_value": "VALUE",
                        "code": "USD",
                        "amount_1000": currency_var
                    }
                }
            )

        if element.get("button_vars"):
            buttons_parameters = {
                "type": "button",
                "sub_type": "url",
                "index": 0,
                "parameters":
                    [{
                        "type": "text",
                        "text": element["button_vars"]
                    }]
            }

    template_header = {
        "type": "header",
        "parameters": header_parameters
    }

    template_body = {
        "type": "body",
        "parameters": body_parameters
    }

    template_footer = {}
    template_buttons = buttons_parameters

    if len(template_header) > 0:
        template_components.append(template_header)

    if len(template_body) > 0:
        template_components.append(template_body)

    if len(template_footer) > 0:
        template_components.append(template_footer)

    if len(template_buttons) > 0:
        template_components.append(template_buttons)

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": whatsapp_number,
        "type": "template",
        "template": {
            "name": template.name,
            "language": {
                "code": template.language
            },
            "components": template_components
        }
    }

    return payload


def compose_text_template_message(template, template_vars):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "PHONE_NUMBER",
        "type": "template",
        "template": {
            "name": "TEMPLATE_NAME",
            "language": {
                "code": "LANGUAGE_AND_LOCALE_CODE"
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "text-string"
                        },
                        {
                            "type": "currency",
                            "currency": {
                                "fallback_value": "VALUE",
                                "code": "USD",
                                "amount_1000": "10"
                            }
                        },
                        {
                            "type": "date_time",
                            "date_time": {
                                "fallback_value": "DATE"
                            }
                        }
                    ]
                }
            ]
        }
    }


def compose_interactive_template_message(template, template_vars):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "PHONE_NUMBER",
        "type": "template",
        "template": {
            "name": "TEMPLATE_NAME",
            "language": {
                "code": "LANGUAGE_AND_LOCALE_CODE"
            },
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "image",
                            "image": {
                                "link": "http(s)://URL"
                            }
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "TEXT_STRING"
                        },
                        {
                            "type": "currency",
                            "currency": {
                                "fallback_value": "VALUE",
                                "code": "USD",
                                "amount_1000": "10"
                            }
                        },
                        {
                            "type": "date_time",
                            "date_time": {
                                "fallback_value": "MONTH DAY, YEAR"
                            }
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": "0",
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": "PAYLOAD"
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": "1",
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": "PAYLOAD"
                        }
                    ]
                }
            ]
        }
    }


def compose_location_template_message(template, template_vars):
    payload = {
        "type": "header",
        "parameters": [
            {
                "type": "location",
                "location": {
                    "latitude": "<LATITUDE>",
                    "longitude": "<LONGITUDE>",
                    "name": "<NAME>",
                    "address": "<ADDRESS>"
                }
            }
        ]
    }


def replace_template_placeholders(obj, vars):
    if isinstance(obj, str):
        return re.sub(r'{{(.*?)}}', lambda match: str(vars.get(match.group(1), match.group(0))), obj)
    elif isinstance(obj, list):
        return [replace_template_placeholders(item, vars) for item in obj]
    elif isinstance(obj, dict):
        return {key: replace_template_placeholders(value, vars) for key, value in obj.items()}
    return obj


def build_whatsapp_components(template: dict, values: dict) -> list[dict]:
    components = []
    param_format = template.get("parameter_format", "POSITIONAL")

    for comp in template.get("components", []):
        ctype = comp["type"]

        # ---------------- HEADER ----------------
        if ctype == "HEADER":
            if comp.get("format") != "TEXT":
                continue  # MEDIA headers have no vars

            vars_ = extract_vars(comp.get("text", ""))
            if vars_:
                components.append({
                    "type": "header",
                    "parameters": [
                        {"type": "text", "text": _require(values, v, "HEADER")}
                        for v in vars_
                    ]
                })

        # ---------------- BODY ----------------
        elif ctype == "BODY":
            vars_ = extract_vars(comp.get("text", ""))
            if vars_:
                if param_format == "NAMED":
                    components.append({
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": _require(values, v, "BODY"),
                                "parameter_name": v,
                            }
                            for v in vars_
                        ],
                    })
                else:
                    components.append({
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": _require(values, v, "BODY")}
                            for v in vars_
                        ],
                    })

        # ---------------- FOOTER ----------------
        elif ctype == "FOOTER":
            if extract_vars(comp.get("text", "")):
                raise ValueError("WhatsApp does not allow variables in FOOTER")

        # ---------------- BUTTONS ----------------
        elif ctype == "BUTTONS":
            for idx, btn in enumerate(comp.get("buttons", [])):
                btn_type = btn.get("type")

                # ✅ FLOW buttons — NO parameters EVER
                if btn_type == "FLOW":
                    components.append({
                        "type": "button",
                        "sub_type": "flow",
                        "index": str(idx),
                    })

                # ✅ QUICK_REPLY — NO parameters EVER
                elif btn_type == "QUICK_REPLY":
                    components.append({
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": str(idx),
                    })

                # ✅ URL buttons — MAY have text parameter
                elif btn_type == "URL":
                    vars_ = extract_vars(btn.get("text", ""))
                    params = []

                    if vars_:
                        params = [
                            {"type": "text", "text": _require(values, v, "BUTTON_URL")}
                            for v in vars_
                        ]

                    button = {
                        "type": "button",
                        "sub_type": "url",
                        "index": str(idx),
                    }
                    if params:
                        button["parameters"] = params

                    components.append(button)

                else:
                    raise ValueError(f"Unsupported button type: {btn_type}")

    return components


def compose_template_based_message(template, phone, namespace, components):
    button = template.get("button", None)
    # components = template.get("components", [])
    currency = template.get("currency", None)
    date_time = template.get("date_time", None)
    parameter = template.get("parameter", None)

    language = {
        "policy": "deterministic",
        "code": template["language"]
    }

    template_object = {
        "namespace": namespace,
        "name": template["name"],
        "language": language,
        "components": components,
    }

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "template",
        "template": template_object,
    }
    return data


def get_template(templates, name):
    if templates is None:
        return None

    for t in templates:
        if t["name"] == name or t["id"] == name:
            return t

    return None


def get_waba_customer_account(customer_waba_id):
    portal_config = PortalConfiguration.objects.first()

    request_data = {
        "fields": "id, name, currency, owner_business_info",
        "access_token": portal_config.fb_system_token
    }
    url = f"https://graph.facebook.com/v21.0/{customer_waba_id}"
    response = requests.get(url, params=request_data)
    return response.json()


def waba_temp_token_swap(auth_token: str, portal_config) -> str:
    """
    Exchange a temporary OAuth code for a long-lived WABA access token.
    Raises:
      - ImproperlyConfigured if any required config is missing
      - requests.exceptions.HTTPError on HTTP errors
      - ValueError if the JSON response is missing the access_token
    """
    # ─── Validate portal_config ─────────────────────────────────────────
    for attr in ("fb_moio_bot_app_id", "fb_moio_bot_app_secret", "my_url"):
        if not getattr(portal_config, attr, None):
            raise ImproperlyConfigured(f"Missing PortalConfiguration.{attr}")

    url = "https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "client_id":     portal_config.fb_moio_bot_app_id,
        "client_secret": portal_config.fb_moio_bot_app_secret,
        "redirect_uri":  f"{portal_config.my_url}fb_oauth_callback/",
        "code":          auth_token,
    }

    # ─── Perform request & raise on bad status ───────────────────────
    response = requests.get(url, params=params)
    response.raise_for_status()  # raises HTTPError for 4xx/5xx

    # ─── Parse & validate JSON ────────────────────────────────────────
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError(f"No access_token in response: {payload!r}")

    # Optional: log token_type and expires_in if present
    token_type = payload.get("token_type")
    expires_in = payload.get("expires_in")
    if token_type and expires_in:
        logger.info(f"Token swap succeeded: type={token_type}, expires_in={expires_in}")

    return access_token


def get_customers_waba_id(user_token: str) -> str:
    """
    Validate the Facebook debug_token response and extract the first WABA ID
    from granular_scopes → target_ids.
    Raises on HTTP errors or missing data.
    """
    portal_config = PortalConfiguration.objects.first()
    if not portal_config or not portal_config.fb_system_token:
        raise ImproperlyConfigured("Missing PortalConfiguration.fb_system_token")

    url = "https://graph.facebook.com/debug_token/"
    params = {
        "input_token": user_token,
        "access_token": portal_config.fb_system_token,
    }

    # 🔥 This will raise requests.exceptions.HTTPError for 4xx/5xx
    response = requests.get(url, params=params)
    response.raise_for_status()

    payload = response.json()
    data = payload.get("data", {})

    scopes = data.get("granular_scopes")
    if not scopes or not isinstance(scopes, list):
        raise ValueError(f"No granular_scopes in debug_token response: {payload}")

    target_ids = scopes[0].get("target_ids")
    if not target_ids or not isinstance(target_ids, list):
        raise ValueError(f"No target_ids in granular_scopes[0]: {scopes[0]}")

    # return the first WABA ID
    return target_ids[0]


def get_customer_waba_phone_numbers(customer_waba_id: str) -> list[dict]:
    """
    Fetch all phone-number objects for a given WABA customer.
    Raises HTTPError on bad status or ValueError if response schema is unexpected.
    """
    portal_config = PortalConfiguration.objects.first()
    if not portal_config or not portal_config.fb_system_token:
        raise ImproperlyConfigured("Missing PortalConfiguration.fb_system_token")

    url = f"https://graph.facebook.com/v21.0/{customer_waba_id}/phone_numbers"
    params = {
        "fields": (
            "id,cc,country_dial_code,display_phone_number,"
            "verified_name,status,quality_rating,search_visibility,"
            "platform_type,code_verification_status"
        ),
        "access_token": portal_config.fb_system_token,
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    payload = response.json()
    data = payload.get("data")
    if data is None or not isinstance(data, list):
        raise ValueError(f"Expected ‘data’ list in phone_numbers response, got: {payload!r}")

    return data


def subscribe_to_webhooks(customer_waba_id: str, fb_system_token) -> dict:
    """
    Subscribe the given WABA customer to app webhooks.
    Raises HTTPError on non-2xx responses or ImproperlyConfigured if token is missing.
    """

    url = f"https://graph.facebook.com/v21.0/{customer_waba_id}/subscribed_apps"
    payload = {"access_token": fb_system_token}

    response = requests.post(url, json=payload)

    result = response.json()
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object from subscribe call, got: {result!r}")

    return result


def unsubscribe_from_webhooks(customer_waba_id: str) -> dict:
    """
    Unsubscribe the given WABA customer from app webhooks.
    Raises HTTPError on non-2xx responses or ImproperlyConfigured if token is missing.
    """
    portal_config = PortalConfiguration.objects.first()
    if not portal_config or not portal_config.fb_system_token:
        raise ImproperlyConfigured("Missing PortalConfiguration.fb_system_token")

    url = f"https://graph.facebook.com/v21.0/{customer_waba_id}/subscribed_apps"
    params = {"access_token": portal_config.fb_system_token}

    response = requests.delete(url, params=params)
    response.raise_for_status()  # raises HTTPError for 4xx/5xx

    result = response.json()
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object from unsubscribe call, got: {result!r}")

    return result


def register_waba_phone_number(phone_waba_id: str, fb_system_token) -> dict:
    """
    Register a WABA phone number by PIN.
    Raises HTTPError on non-2xx responses or ImproperlyConfigured if token is missing.
    """
    portal_config = PortalConfiguration.objects.first()
    if not portal_config or not portal_config.fb_system_token:
        raise ImproperlyConfigured("Missing PortalConfiguration.fb_system_token")

    url = f"https://graph.facebook.com/v21.0/{phone_waba_id}/register"
    payload = {
        "messaging_product": "whatsapp",
        "pin": "000000",
        "access_token": fb_system_token,
    }

    response = requests.post(url, json=payload)

    result = response.json()
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object from register call, got: {result!r}")

    return result
