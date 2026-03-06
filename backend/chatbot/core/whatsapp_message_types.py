from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional, List, Union


# Base model with configuration to forbid extra fields
class WhatsAppBaseModel(BaseModel):
    model_config = {"extra": "forbid"}


# Context sub-model
class Context(WhatsAppBaseModel):
    message_id: str


# Text sub-model
class Text(WhatsAppBaseModel):
    preview_url: Literal["true", "false"]
    body: str


# Image sub-model
class Image(WhatsAppBaseModel):
    link: str
    caption: str


# Audio sub-model
class Audio(WhatsAppBaseModel):
    link: str


# Video sub-model
class Video(WhatsAppBaseModel):
    link: str


# Document sub-model
class Document(WhatsAppBaseModel):
    link: str
    caption: str


# Location sub-model
class Location(WhatsAppBaseModel):
    latitude: str
    longitude: str
    name: str
    address: str


# Contacts sub-models
class ContactAddress(WhatsAppBaseModel):
    street: str
    city: str
    state: str
    zip: str
    country: str
    country_code: str
    type: str


class ContactEmail(WhatsAppBaseModel):
    email: str
    type: str


class ContactName(WhatsAppBaseModel):
    formatted_name: str
    first_name: str
    last_name: str
    middle_name: str
    suffix: str
    prefix: str


class ContactOrg(WhatsAppBaseModel):
    company: str
    department: str
    title: str


class ContactPhone(WhatsAppBaseModel):
    phone: str
    wa_id: str
    type: str


class ContactUrl(WhatsAppBaseModel):
    url: str
    type: str


class Contact(WhatsAppBaseModel):
    addresses: List[ContactAddress]
    birthday: str
    emails: List[ContactEmail]
    name: ContactName
    org: ContactOrg
    phones: List[ContactPhone]
    urls: List[ContactUrl]


# Interactive sub-models
class InteractiveHeader(WhatsAppBaseModel):
    type: Literal["text"]
    text: str


class InteractiveBody(WhatsAppBaseModel):
    text: str


class InteractiveFooter(WhatsAppBaseModel):
    text: str


class InteractiveButtonReply(WhatsAppBaseModel):
    id: str
    title: str


class InteractiveButton(WhatsAppBaseModel):
    type: Literal["reply"]
    reply: InteractiveButtonReply


class InteractiveRow(WhatsAppBaseModel):
    id: str
    title: str
    description: str


class InteractiveProductItem(WhatsAppBaseModel):
    product_retailer_id: str


class InteractiveSection(WhatsAppBaseModel):
    title: str
    rows: Optional[List[InteractiveRow]] = None
    product_items: Optional[List[InteractiveProductItem]] = None


class InteractiveParameters(WhatsAppBaseModel):
    display_text: str
    url: str
    flow_message_version: str
    flow_token: str
    flow_id: str
    flow_cta: str
    flow_action: str


class InteractiveAction(WhatsAppBaseModel):
    buttons: List[InteractiveButton] = Field(default_factory=list)
    button: Optional[str] = None
    sections: List[InteractiveSection] = Field(default_factory=list)
    catalog_id: Optional[str] = None
    name: Optional[Literal["send_location", "cta_url", "flow"]] = None
    parameters: Optional[InteractiveParameters] = None


class Interactive(WhatsAppBaseModel):
    type: Literal["button", "list", "product_list", "location_request_message", "cta_url", "flow"]
    header: Optional[InteractiveHeader] = None
    body: InteractiveBody
    footer: Optional[InteractiveFooter] = None
    action: InteractiveAction


# Main WhatsAppMessage model
class WhatsAppMessage(WhatsAppBaseModel):
    messaging_product: Literal["whatsapp"]
    recipient_type: Optional[Literal["individual"]] = None
    to: str
    context: Optional[Context] = None
    type: Literal["text", "image", "audio", "video", "document", "location", "contacts", "interactive"]
    text: Optional[Text] = None
    image: Optional[Image] = None
    audio: Optional[Audio] = None
    video: Optional[Video] = None
    document: Optional[Document] = None
    location: Optional[Location] = None
    contacts: List[Contact] = Field(default_factory=list)
    interactive: Optional[Interactive] = None

    @model_validator(mode="after")
    def validate_content_fields(self):
        content_fields = {
            "text": self.text,
            "image": self.image,
            "audio": self.audio,
            "video": self.video,
            "document": self.document,
            "location": self.location,
            "contacts": self.contacts,
            "interactive": self.interactive
        }

        expected_field_name = self.type
        expected_field_value = content_fields[expected_field_name]

        # Check if the expected field is provided
        if expected_field_name == "contacts":
            if not self.contacts:  # Must be non-empty for type "contacts"
                raise ValueError("contacts must be non-empty for type 'contacts'")
        elif expected_field_value is None:
            raise ValueError(f"{expected_field_name} must be provided for type '{self.type}'")

        # Validate recipient_type
        if self.type == "contacts":
            if self.recipient_type is not None:
                raise ValueError("recipient_type must be null for type 'contacts'")
        else:
            if self.recipient_type != "individual":
                raise ValueError("recipient_type must be 'individual' for type '{self.type}'")

        # Check that only the expected field is set
        for field_name, field_value in content_fields.items():
            if field_name != expected_field_name:
                if field_name == "contacts":
                    if field_value:  # Must be empty for non-contacts types
                        raise ValueError("contacts must be an empty list for type '{self.type}'")
                elif field_value is not None:
                    raise ValueError(f"{field_name} must be null for type '{self.type}'")

        return self
