import asyncio

from agents import Runner

# from whatsapp_model import WhatsAppMessage
from agents import set_default_openai_key

from chatbot.agents.moio_agents_loader import build_agents_for_tenant
from chatbot.models.chatbot_session import ChatbotSession
from portal.models import TenantConfiguration
import logging

logger = logging.getLogger(__name__)

whatsapp_formatting_instructions = """You are a Formatter service that will provide format to every message following this protocol:
                    When generating a WhatsApp message payload, follow these formatting rules to ensure compliance with the WhatsApp Cloud API:

                    Do not attempt to reply with context unless specified
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

                    Message Type-Specific Rules

                    1. Text Messages ("type": "text")
                    "text.body" is required (max 4096 characters).
                    "text.preview_url" should be "true" if the message contains a URL and should show a preview.

                    Example:
                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": "individual",
                      "to": "+14155552671",
                      "type": "text",
                      "text": {
                        "body": "Hello, check this out: https://example.com",
                        "preview_url": true
                      }
                    }

                    2. Media Messages ("type": "media")
                    Used for sending images, audio, video, and documents.
                    "media.media_type" must be one of: "image", "audio", "video", "document".
                    "media.link" must be a publicly accessible URL or a previously uploaded media ID.
                    "media.caption" is optional (max 1024 characters).
                    "media.filename" is only required for documents.
                    Allowed formats and size limits:
                    Image: JPG, JPEG, PNG (Max 5MB)
                    Audio: AAC, MP3, OPUS (Max 16MB)
                    Video: MP4, 3GP (Max 16MB)
                    Document: PDF, DOC(X), XLS(X), PPT(X) (Max 100MB)

                    Example (Image Message):
                    {
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
                    Example (Document Message with Filename):
                    {
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

                    3. Location Messages ("type": "location")
                    "latitude" and "longitude" are required (decimal format).
                    "name" and "address" are optional but recommended.

                    Example:
                    {
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

                    4. Contact Messages ("type": "contacts")
                    "contacts" must be an array (max 10 contacts per message).
                    Each contact must include a name and at least one phone number.
                    Example:
                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": null,
                      "to": "+14155552671",
                      "type": "contacts",
                      "contacts": [
                        {
                          "name": { "formatted_name": "John Doe", "first_name": "John", "last_name": "Doe" },
                          "phones": [{ "phone": "+1234567890", "type": "CELL" }]
                        }
                      ]
                    }

                    5.  Interactive Messages ("type": "interactive")
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

                    Example (List Message):
                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": "individual",
                      "to": "+14155552671",
                      "type": "interactive",
                      "interactive": {
                        "type": "list",
                        "body": { "text": "Choose an option:" },
                        "footer": { "text": "Powered by WhatsApp" },
                        "action": {
                          "button": "View Options",
                          "sections": [
                            {
                              "title": "Services",
                              "rows": [
                                { "id": "option1", "title": "Consultation", "description": "Book a 1:1 session" },
                                { "id": "option2", "title": "Support", "description": "Get customer support" }
                              ]
                            }
                          ]
                        }
                      }
                    }


                    These messages contain a Call-To-Action (CTA) button that redirects users to a specific URL when clicked. They are categorized as "interactive" messages with a subtype "interactive-cta-url".

                    6. Message Type: Set "type": "interactive-cta-url".

                    Structure:

                    "header" (optional): Short title for the message (max 60 characters).
                    "body" (required): The main message content (max 1024 characters).
                    "footer" (optional): Additional text at the bottom (max 60 characters).
                    "action" (required): Defines the CTA button and its destination:
                    "button": The text on the button (max 20 characters).
                    "url": The URL that opens when the button is clicked (must be a valid URI).
                    Example JSON for a CTA URL Message:
                    {
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

                    7. Reply Button Messages ("type": "button")
                    Can contain up to 3 buttons.
                    Each button must have:
                    "id" (max 256 characters).
                    "title" (max 20 characters).
                    Example (Reply Buttons):
                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": "individual",
                      "to": "+14155552671",
                      "type": "interactive",
                      "interactive": {
                        "type": "button",
                        "body": { "text": "Select an option:" },
                        "action": {
                          "buttons": [
                            { "type": "reply", "reply": { "id": "btn_1", "title": "Order Now" } },
                            { "type": "reply", "reply": { "id": "btn_2", "title": "More Info" } }
                          ]
                        }
                      }
                    }

                    8. Location-Request Messages
                    Location-Request messages ask the user to share their location by displaying a “Send Location” button
                    When the user taps this button, WhatsApp opens a location picker for the user to send their GPS location. These messages are represented as an interactive message with a specific subtype:
                    Type and Subtype: Use "type": "interactive" with "interactive.type": "location_request_message".
                    Body: A text prompt explaining the location request (max 1024 characters, required)

                    Action: Include "action": { "name": "send_location" } to trigger the location picker
                    Header/Footer: Not supported for this message type (only body text is allowed).
                    JSON Example: 
                    A location request message with a prompt text would look like this:
                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": "individual",
                      "to": "+5983212213",
                      "type": "interactive",
                      "interactive": {
                        "type": "location_request_message",
                        "body": { "text": "Please share your location with us." },
                        "action": { "name": "send_location" }
                      }
                    }
                    This format complies with WhatsApp Cloud API’s requirements for interactive location requests, ensuring the user sees a Send Location button.

                    9. Interactive-Flow Message
                    Interactive-Flow messages are a special type of messages used only when a flow_id is provided.

                    Type and Subtype: Use "type": "interactive" with "interactive.type": "flow

                    Header/Body/Footer: You can include optional text in "header", "body", and "footer" to describe the flow (e.g., a title or instructions).
                    Within "parameters", provide the identifiers and settings for the flow:

                    flow_id: The ID of the flow
                    flow_message_version: Version of the flow format (e.g., "3" for current version).
                    flow_token: A token or key issued for your flow (from WhatsApp) to authorize launching it.
                    flow_cta: The text for the Call-To-Action button that opens the flow (e.g., "Book now"). 

                    JSON Example: An interactive flow message might be structured as:

                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": "individual",
                      "to": "+59821332123",
                      "type": "interactive",
                      "interactive": {
                        "type": "flow",
                        "header": { "type": "text", "text": "Example Flow" },
                        "body":   { "text": "Please follow the steps in this flow." },
                        "footer": { "text": "Thank you!" },
                        "action": {
                          "name": "flow",
                          "parameters": {
                            "flow_id": "31231234213123",
                            "flow_message_version": "6.3,
                            "flow_token": "unused",
                            "flow_cta": "Start Now",
                            "flow_action": "navigate",
                            "flow_action_payload": {
                              "screen": "FRIST_ENTRY_SCREEN",
                              "data": { /* optional initial data */ }
                            }
                          }
                        }
                      }
                    }

                    10. Single-Product Messages
                    Single-Product messages showcase one specific product from a WhatsApp Business product catalog. They appear with the product’s image, title, price, and a button to view more details. The schema for these messages uses an interactive object of type “product”:
                    Type and Subtype: "type": "interactive" with "interactive.type": "product"
                    Body/Footer: You can provide a description or promotional text in the "body.text", and optional additional info in "footer.text"

                    Note: Header is not allowed for product messages
                    Action: The "action" object must specify the product to display:
                    "catalog_id": The unique ID of the Facebook catalog linked to your WhatsApp Business account that contains the product

                    "product_retailer_id": The identifier of the specific product in the catalog (this is the product’s SKU or ID in your catalog)
                    JSON Example: A single-product message JSON could be:
                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": "individual",
                      "to": "<PHONE_NUMBER>",
                      "type": "interactive",
                      "interactive": {
                        "type": "product",
                        "body":   { "text": "Check out our featured product of the day!" },
                        "footer": { "text": "Limited time offer." },
                        "action": {
                          "catalog_id": "<CATALOG_ID>",
                          "product_retailer_id": "<PRODUCT_ID>"
                        }
                      }
                    }
                    This will send a message featuring the product identified by <PRODUCT_ID> from the given catalog. The user will see the product’s details and can tap it to view more. According to WhatsApp API rules, a header cannot be set for this type of message
                    , so we use body text (and footer if needed) for any captions or descriptions.

                    11. Multi-Product Messages
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

                    JSON Example: A multi-product message featuring two products might look like:

                    {
                      "messaging_product": "whatsapp",
                      "recipient_type": "individual",
                      "to": "<PHONE_NUMBER>",
                      "type": "interactive",
                      "interactive": {
                        "type": "product_list",
                        "header": { "type": "text", "text": "Our New Arrivals" },
                        "body":   { "text": "Here are some products you might like:" },
                        "footer": { "text": "Tap a product to view details or purchase." },
                        "action": {
                          "catalog_id": "<CATALOG_ID>",
                          "sections": [
                            {
                              "title": "Featured",
                              "product_items": [
                                { "product_retailer_id": "<PRODUCT_ID_1>" },
                                { "product_retailer_id": "<PRODUCT_ID_2>" }
                              ]
                            }
                          ]
                        }
                      }
                    }
                    """,


def agent_processor(user_input: str, session: ChatbotSession):

    config = TenantConfiguration.objects.get(tenant=session.tenant)
    set_default_openai_key(config.openai_api_key)

    lista_de_agentes = build_agents_for_tenant(session.tenant)  # Aquí se cargan todos los agentes disponibles, las herramientas deben estar cargadas
    thread = []                                                 # Reemplazar con la Thread real de la session
    running_agent = lista_de_agentes[session.agent_id]          # Seleccionar el agente adecuado para la session (el agente por defecto debe asignarse al crear una nuave)

    user_utterance = {"role": "user", "content": user_input}    # Agregar el input del usuario al thread
    thread.append(user_utterance)

    context = {                                                 # Opcion para pasar Contexto al Agente
        "session": session.session,
        "tenant": session.tenant,
        "contact": {
            "name": session.contact.whatsapp_name,
            "email": session.contact.email,
            "phone": session.contact.phone,
        },
        "summary": "",
    }

    try:

        result = asyncio.run(Runner.run(running_agent, input=thread, context=context))  # Ejecutar el agente agregando la thread y el contexto

        print(result.final_output)
        print(f'Last agent: {result.last_agent.name}')

        # print(result.to_input_list())
        running_agent = lista_de_agentes[result.last_agent.name]                        # Reemplazar con la actualization del agente a cargo de la session

        print(result.to_input_list())

        assistant_utterance = {"role": "assistant", "content": str(result.final_output)}
        thread.append(assistant_utterance)                                              # Agregar la respuesta a la conversion

        return result.final_output

    except Exception as e:
        logger.error(e)
        return None

