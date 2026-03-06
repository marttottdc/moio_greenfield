import inspect
import json
import re
import uuid
import logging

from django.utils import timezone
from pgvector.django.functions import L2Distance, CosineDistance
from crm.lib.woocommerce_api import WooCommerceAPI

from crm.models import Stock, ProductVariant, Product, Tag, EcommerceOrder, ActivityRecord, KnowledgeItem, VisibilityChoices
from crm.core.tickets import create_ticket
from chatbot.models.chatbot_session import ChatbotSession
# from crm.lib.crm_search import search_by_tag, search_text, search_by_product
from moio_platform.lib.tools import function_to_spec

from moio_platform.lib.google_maps_api import GoogleMapsApi, haversine
from moio_platform.lib.wordpress_api import WordPressAPIClient
from moio_platform.lib.openai_gpt_api import MoioOpenai
from portal.context_utils import current_tenant
from portal.models import TenantConfiguration, PortalConfiguration
from django.dispatch import receiver
from django.dispatch import Signal
from chatbot.core.messenger import Messenger
from agents import Agent, WebSearchTool, FileSearchTool, function_tool, Runner, RunHooks, AgentOutputSchema, set_default_openai_key, FunctionTool,  RunContextWrapper

# Define a custom signal
comfort_message = Signal()

logger = logging.getLogger(__name__)


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


def get_available_tools():

    available_tools = []
    tools = [method for method in dir(MoioAssistantTools) if callable(getattr(MoioAssistantTools, method)) and not method.startswith("__")]

    for tool in tools:

        # func_spec = get_function_spec(getattr(MoioAssistantTools, tool))
        func_spec = function_to_spec(getattr(MoioAssistantTools, tool))
        available_tools.append(func_spec)

    return available_tools


def get_named_period(period_name, date_format="%Y-%m-%d"):
    current_date = timezone.localtime(timezone.now())

    if period_name.lower() == "month to date":
        start_date = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = current_date

    elif period_name.lower() == "year to date":
        start_date = current_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
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
    moio_messenger = Messenger(channel=channel, config=config, client_name="comfort")
    moio_messenger.just_reply(message, phone)

    logger.error(f"Sending comfort message {sender}: {message}")


class MoioAssistantTools:

    def __init__(self, session: ChatbotSession):
        self.assistant_id = session.assistant_id
        self.tenant_id = session.tenant_id
        self.contact = session.contact
        self.cart = []
        self.session = session

    def assign_assistant(self, assistant_id):
        """
        After reviewing the available assistants, return the id of the best match  to continue with the conversation
        :param assistant_id: id of the assistant to be assigned
        """
        self.assistant_id = assistant_id
        print(self.assistant_id)
        return assistant_id

    def search_product(self, search_term):
        """
        Search products that match the user intent
        :param search_term: search term to look for will be converted to embedding for semantic search

        """
        print(f"Search term {search_term}")
        try:
            comfort_message.send(sender="search_product", message="Buscando...", tenant_id=self.tenant_id, phone=self.contact.phone, channel=self.session.channel)
        except Exception as e:
            print(e)
        config = TenantConfiguration.objects.get(tenant=self.tenant_id)

        available_products = []
        # Assuming you've already populated the embedding field
        mo = MoioOpenai(api_key=config.openai_api_key, default_model=config.openai_default_model)
        search_term_embedding = mo.get_embedding(search_term)
        matches = Tag.objects.filter(tenant=config.tenant).order_by(L2Distance('embedding', search_term_embedding)).annotate(l2_distance=L2Distance('embedding', search_term_embedding), cos_distance=CosineDistance('embedding', search_term_embedding)).filter(l2_distance__lt=1.2)[:5]

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
                if item.fb_product_id:
                    recommended_products.append(product)
                else:
                    logger.warning("Product missing data %s", item.name)

            if match.l2_distance < 1 or match.cos_distance < 0.5:
                result_item = {
                    "search_match": match.name,
                    "l2_distance": match.l2_distance,
                    "cosine_distance": match.cos_distance,
                    "recommended_products": json.dumps(recommended_products),
                    "recommended_message_type": "multi_product_message"
                }
                results.append(result_item)
                return json.dumps(results)
            else:
                result_item = {
                    "search_match": match.name,
                    "disambiguation_required": True,
                    "recommended_message_type": "interactive_list"
                }
                disambiguation_matches.append(result_item)
                return json.dumps(disambiguation_matches)

    def search_product_v2(self, search_term):
        """
        Search products that match the user intent
        :param search_term: search term to look for will be converted to embedding for semantic search

        """
        print(f"Search term {search_term}")
        try:
            comfort_message.send(sender="search_product", message="Buscando...", tenant_id=self.tenant_id,
                                 phone=self.contact.phone, channel=self.session.channel)
        except Exception as e:
            print(e)

        config = TenantConfiguration.objects.get(tenant_id=self.tenant_id)

        available_products = []
        # Assuming you've already populated the embedding field
        mo = MoioOpenai(api_key=config.openai_api_key, default_model=config.openai_default_model)
        search_term_embedding = mo.get_embedding(search_term)
        tag_matches = Tag.objects.filter(tenant=config.tenant).order_by(
            L2Distance('embedding', search_term_embedding)).annotate(
            l2_distance=L2Distance('embedding', search_term_embedding),
            cos_distance=CosineDistance('embedding', search_term_embedding)).filter(l2_distance__lt=1, cos_distance__lt=0.5)

        print("Matching Tags Found")
        for tm in tag_matches:
            print(tm.name, tm.l2_distance, tm.cos_distance)
        # Prefetch the related products for those tags
        if len(tag_matches) > 0:
            products = Product.objects.filter(tags__in=tag_matches).distinct()[:3]
            print("Product matching tags found")
            for p in products:
                print(p.name, p.description)
        else:
            products = Product.objects.filter(tenant=config.tenant).order_by(
                L2Distance('embedding', search_term_embedding)).annotate(
                l2_distance=L2Distance('embedding', search_term_embedding),
                cos_distance=CosineDistance('embedding', search_term_embedding)).filter(l2_distance__lt=1, cos_distance__lt=0.5)

            print("Products matching search found")
            for p in products:
                print(p.name, p.description, p.l2_distance, p.cos_distance)

        if len(products) == 0:
            tag_matches = Tag.objects.filter(tenant=config.tenant).order_by(
                L2Distance('embedding', search_term_embedding)).annotate(
                l2_distance=L2Distance('embedding', search_term_embedding),
                cos_distance=CosineDistance('embedding', search_term_embedding))[:3]
            print("Quisiste decir ?")
            for tm in tag_matches:
                print(tm.name, tm.l2_distance, tm.cos_distance)

        recommended_products = []
        for item in products:
            product = {
                'catalog_id': config.whatsapp_catalog_id,
                'id': item.fb_product_id,
                'sku': item.sku,
                'name': item.name,
                'price': item.price,
                'url': item.permalink,
                'attributes': json.dumps(item.attributes),
            }
            if item.fb_product_id:
                recommended_products.append(product)
            else:
                logger.warning("Product missing data %s", item.name)

        return json.dumps(recommended_products)

    def cart_setup(self):
        """
        if user requires to start an order, we must set up a cart
        """

        response = {

            "cart_ready": "true",
            "cart_id": uuid.uuid4().__str__()
        }
        return json.dumps(response)

    def order_status(self, order_number: str = "", customer_phone_number: str = "", customer_email: str = ""):
        """
        checks for the delivery tracking status of an order
        :param order_number:
        :param customer_phone_number:
        :param customer_email:
        :return:
        """
        order = EcommerceOrder.objects.filter(customer_phone_number=self.contact.phone)
        return f"Order {order_number} is in progress"

    def create_ticket(self, description: str, service="default"):
        """
        Any requirement from the user that cannot be solved by delivering available information, or by acquiring data form the available tools will create a ticket
        In the same language of the conversation.
        :param description:
        :param service: one of "Customer Service", "Sales", "Tech Support"
        :return:
        """
        comfort_message.send(sender="search_product",
                             message="Registrando Solicitud",
                             tenant_id=self.tenant_id,
                             phone=self.contact.phone,
                             channel=self.session.channel)

        ticket = create_ticket(contact=self.contact, tenant_id=self.tenant_id, description=description, service=service, origin_session=self.session)
        ticket.save()

        if ticket:
            # Emit ticket.created event for flow triggers and real-time updates
            try:
                from crm.events.ticket_events import emit_ticket_created
                from uuid import UUID
                # Use a system actor for agent-created tickets
                system_actor_id = UUID("00000000-0000-0000-0000-000000000000")
                emit_ticket_created(ticket, system_actor_id)
            except Exception as e:
                logger.warning(f"Failed to emit ticket creation event: {e}")
            
            portal_config = PortalConfiguration.objects.first()

            response = {
                "ticket_created": "true",
                "ticket_id": ticket.id.__str__(),
                "ticket_description": description,
                "ticket_url": f"{portal_config.my_url}crm/tickets/public/{ticket.id.__str__()}",
                "recommended_message_type": "interactive_cta"
            }
        else:
            response = {
                "ticket_created": "false",
            }

        return json.dumps(response)

    def add_to_cart(self, cart_id: str, sku: str, quantity: str):
        self.cart.append(sku)
        response = {
            "success": "true",
            "cart": self.cart
        }
        return json.dumps(response)

    def customer_lookup(self, phone: str):
        pass

    def register_lead(self, phone: str, name: str):
        pass

    def create_payment_link(self, amount):
        pass

    def review_shipping_requirements(self, order):
        pass

    def send_order_to_fulfillment(self, order):
        pass

    def send_tracking_code(self, order, tracking_code):
        pass

    def search_nearby_pos(self, address: str = "", latitude: float = 0, longitude: float = 0, results: int = 3):
        """
        Buscar puntos de venta o de servicio cercanos a la ubicación del usuario
        :param address: if user sent an address, city or place of reference, do not use for coordinates.
        :param latitude: latitude of the user location
        :param longitude: longitude of the user location
        :param results: quantity of results to return

        """
        comfort_message.send(sender="search_product",
                             message="Buscando ubicaciones cercanas...",
                             tenant_id=self.tenant_id,
                             phone=self.contact.phone,
                             channel=self.session.channel)

        print(f"Address: {address}")
        print(f"Latitude: {latitude}, Longitude: {longitude}")

        config = TenantConfiguration.objects.get(tenant=self.tenant_id)
        maps = GoogleMapsApi(config)

        if latitude != 0 and longitude != 0:

            user_location = {
                "latitude": latitude,
                "longitude": longitude
            }
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
                        "address": address,
                        "result": "could not geocode, try searching knowledge or asking for location"
                    }
                    return json.dumps(data)

            else:
                data = {
                    "address": address,
                    "result": "could not geocode, try searching knowledge or asking for location"
                }
                return json.dumps(data)

            # distance to stores

        else:
            data = {
                "result": "No location or address received, ask the user for either"
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

            distance = haversine(user_location["latitude"], user_location["longitude"], store_latitude, store_longitude)

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
        sorted_places = sorted(recommended_stores, key=lambda item: item["distance"])[:int(results)]
        # Sorted_places is a list from nearest to furthest

        if len(sorted_places) == 0:
            data = {
                "result": "no places found, try search_knowledge"
            }
            return json.dumps(data)
        elif len(sorted_places) == 1:
            data = {
                "recommended_message_type": "interactive_cta or text if has no url ",
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

    def get_tips(self, search_term):
        """
        Buscar la base de conocimiento para ofrecer soluciones y consejos
        :param search_term:

        """
        config = TenantConfiguration.objects.get(tenant=self.tenant_id)
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

    def search_knowledge(self, search_term):
        """
        Buscar la base de conocimientos para responder a cualquier consulta
        Esta es la fuente oficial de información.
        :param search_term: Search term to look for verbatim user input

        """
        print(f"Search term {search_term}")
        comfort_message.send(sender="search_product",
                             message=f"Investigando {search_term}",
                             tenant_id=self.tenant_id,
                             phone=self.contact.phone, channel=self.session.channel)

        config = TenantConfiguration.objects.get(tenant=self.tenant_id)

        # Assuming you've already populated the embedding field
        mo = MoioOpenai(api_key=config.openai_api_key, default_model=config.openai_default_model)
        search_term_embedding = mo.get_embedding(search_term)
        matches = KnowledgeItem.objects.filter(tenant=config.tenant, visibility=VisibilityChoices.PUBLIC).order_by(
            L2Distance('embedding', search_term_embedding)).annotate(
            l2_distance=L2Distance('embedding', search_term_embedding),
            cos_distance=CosineDistance('embedding', search_term_embedding)).filter(l2_distance__lt=1.2)[:5]

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

    def end_conversation(self, conversation_summary):
        """
        function required every time the user ends the conversation or assistant understands conversation has ended
        :conversation_summary: A summary of the conversation, include important details like, search terms, recommendations provided, user mood. In the same language of the conversation

        """
        print('Ending Conversation')

        self.session.final_summary = conversation_summary
        self.session.save()

        response = {"end_conversation": "true"}
        self.session.close()

        return json.dumps(response)

    def get_satisfaction_level(self, satisfaction_level):
        """
        use this function to store the satisfaction level of the user in a scale from 1 to 10
        :param satisfaction_level:

        """
        print(f'Satisfaction level: {satisfaction_level}')

        self.session.csat = satisfaction_level
        self.session.save()

        response = {"saved": "true"}

        return json.dumps(response)

    def register_activity(self, data):
        """
        Register activity like an interactive message content received
        :param data: a json object with the activity data
        """
        try:
            config = TenantConfiguration.objects.get(tenant_id=self.tenant_id)
            new_activity = ActivityRecord.objects.create(
                tenant=config.tenant,
                content=data,
                source="chatbot")
            new_activity.save()
            response = {"data received": "true"}
            return json.dumps(response)

        except Exception as e:
            return json.dumps({"error": str(e)})

    def contact_update(self, email="", fullname=""):
        """
        when data from user is acquired, update the contact.
        :param email: "contact email"
        :param fullname: "contact fullname"

        """
        data = {}
        update = False
        if self.contact.email != email and email != "":

            self.contact.email = email.lower()
            update = True

        if self.contact.fullname != fullname and fullname != "":
            self.contact.fullname = fullname.title()
            update = True

        if update:
            try:
                self.contact.save()
                return json.dumps({"updated": "true"})

            except Exception as e:
                print(e)

        return json.dumps({"updated": "false"})

    def create_order(self, first_name, last_name, phone, address, city, postal_code, email, products):
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

        config = TenantConfiguration.objects.get(tenant=self.tenant_id)
        woo = WooCommerceAPI(
            url=config.woocommerce_site_url,
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

    def output_formatting_instrucions(self, message_type):
        """
        Provides formatting instruccions for the message
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
              "messaging_product": "whatsapp",
              "recipient_type": None,
              "to": "+14155552671",
              "type": "contacts",
              "contacts": [
                {
                  "name": {
                      "formatted_name": "John Doe",
                      "first_name": "John", "last_name": "Doe"
                  },
                  "phones": [
                      {
                          "phone": "+1234567890",
                          "type": "CELL"
                      }
                  ]
                }
              ]
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
                        "body": {"text": "Choose an option:"},
                        "footer": {"text": "Powered by WhatsApp"},
                        "action": {
                          "button": "View Options",
                          "sections": [
                            {
                              "title": "Services",
                              "rows": [
                                {"id": "option1", "title": "Consultation", "description": "Book a 1:1 session"},
                                {"id": "option2", "title": "Support", "description": "Get customer support"}
                              ]
                            }
                          ]
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
                    "body": {"text": "Select an option:"},
                    "action": {
                      "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "btn_1",
                                "title": "Order Now"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "btn_2",
                                "title": "More Info"
                            }
                        }
                      ]
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
                    "body":   {
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
                        "type": "text", "text": "Our New Arrivals"
                    },
                    "body": {
                        "text": "Here are some products you might like:"
                    },
                    "footer": {
                        "text": "Tap a product to view details or purchase."
                    },
                    "action": {
                        "catalog_id": "<CATALOG_ID>",
                        "sections": [
                            {
                                "title": "Featured",
                                "product_items": [
                                    {
                                        "product_retailer_id": "<PRODUCT_ID_1>"
                                    },
                                    {
                                        "product_retailer_id": "<PRODUCT_ID_2>"
                                    }
                                ]
                            }
                        ]
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

        data = {
            "instructions": instructions,
            "example": example
        }

        return json.dumps(data)
