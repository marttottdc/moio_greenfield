

import json
from chatbot.core.smart_reply_prompts import smart_composer_instructions, whatsapp_messages_schema

from django.conf import settings


from chatbot.lib.whatsapp_client_api import WhatsappBusinessClient, WhatsappMessage, WaMessageLog, compose_text_message, compose_image_message, compose_audio_message, compose_video_message, compose_document_message, compose_location_message, compose_reply_2button_message, compose_reply_1button_message, compose_reply_3button_message, compose_require_location, compose_list_message, auto_compose
import logging

from moio_platform.lib.openai_gpt_api import MoioOpenai
from moio_platform.lib.tools import function_to_spec, validate_object
from chatbot.core.whatsapp_message_types import WhatsAppMessage


logger = logging.getLogger(__name__)

tools = [compose_reply_3button_message,
         compose_reply_1button_message,
         compose_list_message,
         compose_require_location,
         compose_audio_message,
         compose_image_message,
         compose_video_message,
         compose_document_message,
         compose_text_message,
         compose_reply_1button_message,
         compose_reply_2button_message,
         compose_reply_3button_message,
         compose_location_message]


def execute_tool_call(tool_call, tools_map):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    print(f"Assistant: {name}({args})")

    # call corresponding function with provided arguments
    return tools_map[name](**args)


class Colors:
    RESET = '\033[0m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    PURPLE = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'


class Messenger:
    def __init__(self, channel, config, client_name):
        self.channel = channel
        self.wa = WhatsappBusinessClient(config)
        self.ai = MoioOpenai(api_key=config.openai_api_key, default_model=config.openai_default_model)
        self.client_name = client_name

    def tool_based_composer(self, reply, phone):
        tool_schemas = [function_to_spec(tool) for tool in tools]

        message = self.ai.tool_calling(
            instructions=smart_composer_instructions,
            prompt=f"content:{reply} , to{phone}",
            tool_schemas=tool_schemas,
            model="gpt-4o-mini",

        )

        composed_messages = []
        tools_map = {tool.__name__: tool for tool in tools}

        for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, tools_map)

            # add result back to conversation
            result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }
            composed_messages.append(result_message["content"])

        return composed_messages

    def smart_composer(self, reply, phone):

        resultado = self.ai.structured_response(data=reply, system_instructions=smart_composer_instructions, output_format=whatsapp_messages_schema, model="gpt-4o", store=True)
        formatted_msg = json.loads(resultado)
        formatted_msg["to"] = phone

        return formatted_msg

    def _is_send_success(self, result):
        """Helper to check if send_message result indicates success."""
        if isinstance(result, dict):
            return result.get("success", False)
        return bool(result)

    def smart_reply(self, reply, phone):

        if reply is None:
            reply = "Tenemos problemas técnicos, por favor intenta más tarde"
            error_msg = compose_text_message(reply, phone)
            return self._is_send_success(self.wa.send_message(error_msg, self.client_name))

        try:

            if type(reply) is list:
                for reply_item in reply:
                    formatted_msg = self.smart_composer(reply_item, phone)
                    print(f'mensaje formateado:{formatted_msg}')

                    self.wa.send_message(formatted_msg, self.client_name)

        except Exception as e:
            if settings.DEBUG:
                exception_msg = compose_text_message(e.__str__(), phone)
                return self._is_send_success(self.wa.send_message(exception_msg, self.client_name))

    def structured_reply(self, reply, phone):

        if type(reply) is str:
            try:
                msg = json.loads(reply)
                msg["to"] = phone

                return self._is_send_success(self.wa.send_message(msg, self.client_name))

            except Exception as e:
                logger.error(f"{reply} : {str(e)}")
                return False

        elif type(reply) is list:
            logger.info(f"Received {len(reply)} part reply")
            success = True
            for msg in reply:
                if type(msg) is str:
                    msg = json.loads(msg)
                    msg["to"] = phone
                    result = self.wa.send_message(msg, self.client_name)
                    success = success and self._is_send_success(result)

            return success

        elif type(reply) is dict:
            return self._is_send_success(self.wa.send_message(reply, self.client_name))

        elif type(reply) is WhatsAppMessage:
            return self._is_send_success(self.wa.send_message(reply, self.client_name))

        else:
            logger.error(f"{reply} : {type(reply)}")
            self.just_reply(reply, phone)

    def _send_text_items_with_report(self, items, phone):
        report = {
            "success": True,
            "sent_items": [],
            "failed_items": [],
        }

        for item in items:
            text_item = item if isinstance(item, str) else str(item)
            msg = compose_text_message(text_item, phone)
            result = self.wa.send_message(msg, self.client_name)
            item_success = self._is_send_success(result)

            if item_success:
                report["sent_items"].append(text_item)
            else:
                report["failed_items"].append(text_item)
                report["success"] = False

        return report

    def just_reply_with_report(self, reply, phone):

        if reply is None:
            reply = "Tenemos problemas técnicos, por favor intenta más tarde"

        if type(reply) is str:
            return self._send_text_items_with_report([reply], phone)

        return self._send_text_items_with_report(reply, phone)

    def just_reply(self, reply, phone):
        report = self.just_reply_with_report(reply, phone)
        return report["success"]

    def reply_email(self, reply, recipient):

        print(reply, recipient)