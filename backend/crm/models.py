import hashlib
import urllib
import uuid
import hmac
from decimal import Decimal

from django.contrib.auth import get_user_model

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from pgvector.django import VectorField
from django.utils.translation import gettext_lazy as _

from jwt import decode as jwt_decode, InvalidTokenError

from moio_platform import settings
from moio_platform.lib.openai_gpt_api import MoioOpenai
from moio_platform.settings import AUTH_USER_MODEL
from central_hub.context_utils import current_tenant
from central_hub.models import Tenant, TenantScopedModel

import phonenumbers
from phonenumbers import carrier, parse, NumberParseException, format_number
from chatbot.models.agent_configuration import AgentConfiguration


class VisibilityChoices(models.TextChoices):
    PUBLIC = 'public', 'Public'
    INTERNAL = 'internal', 'Internal'
    CONFIDENTIAL = 'confidential', 'Confidential'
    RESTRICTED = 'restricted', 'Restricted'


class ContactTypeChoices(models.TextChoices):
    LEAD = 'lead', 'Lead'
    RECURRENT = 'recurrent', 'Recurrent'
    EXPERT = 'expert', 'Expert'
    CUSTOMER = 'customer', 'Customer'
    VIP = 'vip', 'VIP'
    ADMIN = 'admin', 'Admin'
    INTERNAL = 'internal', 'Internal Contact',
    USER = 'user', 'User Contact'


class TicketOriginChoices(models.TextChoices):
    MANUAL = 'manual', 'Manual'
    CHATBOT = 'chatbot', 'Chatbot Conversation'
    WEB_FORM = 'web_form', 'Web Form'
    API = 'api', 'API'
    EMAIL = 'email', 'Email Import'
    PHONE = 'phone', 'Phone Call'
    FLOW = 'flow', 'Automated Flow'
    OTHER = 'other', 'Other'


class ContactType(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=20, choices=ContactTypeChoices.choices, default=ContactTypeChoices.LEAD)
    description = models.TextField(blank=True, default="")
    color = models.CharField(max_length=20, blank=True, default="")
    is_default = models.BooleanField(default=False)
    default_agent = models.ForeignKey(AgentConfiguration, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.is_default and self.tenant_id:
            ContactType.objects.filter(tenant=self.tenant, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Contact Type'
        verbose_name_plural = 'Contact Types'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_contact_type_name_per_tenant'
            )
        ]


class ContactManager(models.Manager):
    def search(self, search_word):
        return self.filter(
            Q(fullname__icontains=search_word) |
            Q(email__icontains=search_word) |
            Q(phone__icontains=search_word) |
            Q(whatsapp_name__icontains=search_word), tenant=current_tenant.get()
        )

    def all(self):
        return self.filter(tenant=current_tenant.get())


class Contact(TenantScopedModel):
    """
    Contact is a Person with contact data usually we have the phone, and the fullname or at least whatsapp_name (if the source was whatsapp) or fullname, email and phone for other sources
    source is who or what created the model
    ctype is the type of the contact, those are dynamically creatd by tenants but accessible via ctype__name (examples are Lead, User, Vip, Expert, Customer)
    """

    user_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4, editable=False, primary_key=True)
    fullname = models.CharField(max_length=100, null=True, default='', blank=True)
    email = models.CharField(max_length=100, null=True, default='', blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True, default='')
    whatsapp_name = models.CharField(max_length=100, null=True, default='', blank=True)
    created = models.DateTimeField(auto_now_add=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    source = models.CharField(max_length=40, null=True, default='', blank=True)
    ctype = models.ForeignKey(ContactType, on_delete=models.SET_NULL, null=True, default=None)
    linked_user = models.OneToOneField(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contact_profile'
    )
    company = models.CharField(max_length=100, null=True, default='', blank=True)
    image = models.ImageField(upload_to="faces/", null=True, blank=True)  # stored still frame
    embedding = VectorField(dimensions=128, null=True, blank=True)  # match your encoder

    # ---------- Identity & names ----------
    first_name = models.CharField(max_length=80, blank=True, default="")
    last_name = models.CharField(max_length=80, blank=True, default="")
    display_name = models.CharField(max_length=120, blank=True, default="")
    nickname = models.CharField(max_length=80, blank=True, default="")
    initials = models.CharField(max_length=8, blank=True, default="")
    dob = models.DateField(null=True, blank=True)
    language = models.CharField(max_length=10, blank=True, default="")  # "es", "en-US"
    timezone = models.CharField(max_length=64, blank=True, default="")

    # ---------- Communication ----------
    mobile = models.CharField(max_length=20, blank=True, default="")
    alt_phone = models.CharField(max_length=20, blank=True, default="")
    email_secondary = models.CharField(max_length=120, blank=True, default="")
    preferred_channel = models.CharField(max_length=20, blank=True, default="")  # email|whatsapp|sms|call
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    do_not_contact = models.BooleanField(default=False)
    is_blacklisted = models.BooleanField(default=False)
    bounced = models.BooleanField(default=False)
    bounce_reason = models.CharField(max_length=200, blank=True, default="")

    # ---------- Org / role ----------
    title = models.CharField(max_length=120, blank=True, default="")
    department = models.CharField(max_length=120, blank=True, default="")
    seniority = models.CharField(max_length=40, blank=True, default="")
    company_website = models.URLField(blank=True, default="")

    # ---------- Addresses (JSON + primary snapshot) ----------
    addresses = models.JSONField(default=list, blank=True)  # list of address dicts (see schema note below)
    primary_address_id = models.UUIDField(null=True, blank=True)

    primary_country = models.CharField(max_length=2, blank=True, default="")
    primary_city = models.CharField(max_length=80, blank=True, default="")
    primary_postal_code = models.CharField(max_length=20, blank=True, default="")
    primary_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    primary_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    primary_geohash = models.CharField(max_length=16, blank=True, default="")

    # Address JSON item (example shape):
    # {
    #   "id": "uuid-string",
    #   "kind": "home|work|billing|shipping|other",
    #   "label": "Short label",
    #   "lines": ["Street 123", "Floor 3"],
    #   "city": "Montevideo",
    #   "region": "Montevideo",
    #   "postal_code": "11300",
    #   "country_code": "UY",
    #   "location": {"lat": -34.9011, "lon": -56.1645, "geohash": "6q6p..."},
    #   "accuracy": "rooftop|range|approx",
    #   "is_primary": true,
    #   "since": "2025-01-01", "until": null,
    #   "meta": {"provider": "google", "place_id": "..."}
    # }

    # ---------- Lifecycle / ownership ----------
    status = models.CharField(max_length=20, blank=True, default="")  # lead|prospect|customer|churned
    stage = models.CharField(max_length=40, blank=True, default="")  # pipeline stage
    owner = models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts")
    score = models.IntegerField(null=True, blank=True)
    created_by = models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="contacts_created")
    updated = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)  # any interaction
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)

    # ---------- Marketing / attribution ----------
    campaign = models.CharField(max_length=80, blank=True, default="")
    utm_source = models.CharField(max_length=80, blank=True, default="")
    utm_medium = models.CharField(max_length=80, blank=True, default="")
    utm_campaign = models.CharField(max_length=80, blank=True, default="")
    utm_term = models.CharField(max_length=120, blank=True, default="")
    utm_content = models.CharField(max_length=120, blank=True, default="")
    referrer_url = models.URLField(blank=True, default="")
    consent_email = models.BooleanField(default=False)
    consent_whatsapp = models.BooleanField(default=False)
    consent_updated_at = models.DateTimeField(null=True, blank=True)

    # ---------- Social / web ----------
    website = models.URLField(blank=True, default="")
    linkedin = models.URLField(blank=True, default="")
    twitter = models.URLField(blank=True, default="")
    instagram = models.URLField(blank=True, default="")
    facebook = models.URLField(blank=True, default="")
    github = models.URLField(blank=True, default="")
    telegram = models.CharField(max_length=100, blank=True, default="")

    # ---------- Commerce / value ----------
    external_customer_id = models.CharField(max_length=120, blank=True, default="")
    currency = models.CharField(max_length=3, blank=True, default="")
    lifetime_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_orders = models.IntegerField(null=True, blank=True)
    last_order_at = models.DateTimeField(null=True, blank=True)
    loyalty_tier = models.CharField(max_length=40, blank=True, default="")
    loyalty_points = models.IntegerField(null=True, blank=True)

    # ---------- LLM brief (large & regenerable) ----------
    brief_facts = models.JSONField(default=dict, blank=True)  # structured facts/preferences/interests
    brief_text = models.TextField(blank=True, default="")  # long running summary (no strict cap)
    brief_version = models.PositiveSmallIntegerField(default=1)
    brief_updated_at = models.DateTimeField(null=True, blank=True)
    interactions_count = models.IntegerField(default=0)
    last_interaction_at = models.DateTimeField(null=True, blank=True)

    # ---------- National ID (sensitive) ----------
    id_country = models.CharField(max_length=2, blank=True, default="")  # ISO-3166-1
    id_type = models.CharField(max_length=20, blank=True, default="")  # "dni"|"ci"|"passport"|...
    id_last4 = models.CharField(max_length=4, blank=True, default="")
    id_hash = models.CharField(max_length=64, blank=True, default="")  # SHA-256 of normalized ID
    id_encrypted = models.BinaryField(null=True, blank=True)  # optional: pgcrypto/fernet ciphertext
    id_verified_at = models.DateTimeField(null=True, blank=True)

    # ---------- Data hygiene / merging ----------
    dedupe_hash = models.CharField(max_length=64, blank=True, default="")
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="merged_contacts")
    is_deleted = models.BooleanField(default=False)  # soft delete
    notes_count = models.IntegerField(default=0)

    # ---------- Flexible blobs ----------
    external_ids = models.JSONField(default=dict, blank=True)  # {"shopify":"...", "woo":"...", "wa_id":"..."}
    preferences = models.JSONField(default=dict, blank=True)  # {"contact_time":"morning","channels":["whatsapp"]}
    traits = models.JSONField(default=dict, blank=True)  # lightweight CDP-style traits
    tags = models.JSONField(default=list, blank=True)  # or M2M Tag table

    objects = ContactManager()

    class Meta:
        ordering = ['created']
        constraints = [
            models.UniqueConstraint(
                fields=['phone', 'tenant'],
                name='unique_phone_tenant',
                condition=Q(phone__isnull=False) & ~Q(phone='')
            ),
            models.UniqueConstraint(
                fields=['email', 'tenant'],
                name='unique_email_tenant',
                condition=Q(email__isnull=False) & ~Q(email='')
            )
        ]

    def __str__(self) -> str:
        """
        label priority:
            fullname → whatsapp_name → email → phone → user_id
        plus "@ company" if company present.
        """

        def clean(val: str | None) -> str:
            """Return val.strip() or '' if val is None / empty."""
            return val.strip() if val else ""

        label = (
                clean(self.fullname)
                or clean(self.whatsapp_name)
                or clean(self.email)
                or clean(self.phone)
                or str(self.user_id)
        )

        company = clean(self.company)
        return f"{label} @ {company}" if company else label

    @classmethod
    def create_or_update(cls, tenant, **kwargs):
        email = kwargs.get('email', '').strip()
        fullname = kwargs.get('fullname', '')
        whatsapp_name = kwargs.get('whatsapp_name', '')
        source = kwargs.get('source', '')
        role = kwargs.get('role', '')
        phone = kwargs.get('phone', '')
        type = kwargs.get('type', None)

        # Always require the tenant.
        query = Q(tenant=tenant)

        # Construct the Q object for flexible querying
        if email == "" and phone == "":
            raise ValueError("Either email or phone must be set")

        else:
            try:

                formatted_phone = format_number(parse(phone), phonenumbers.PhoneNumberFormat.E164)
                print(f'formatted_number: {formatted_phone}')

                # If both phone and email are provided, add an OR condition.
                if formatted_phone and email != "":
                    query &= (Q(phone=formatted_phone) | Q(email=email))
                # If only phone is provided, add that filter.
                elif formatted_phone:
                    query &= Q(phone=formatted_phone)
                # If only email is provided, add that filter.
                elif email != "":
                    query &= Q(email=email)

            except phonenumbers.NumberParseException:

                raise ValueError(f"Invalid phone number {phone}")

        try:
            # Try to find an instance matching any of the provided criteria

            new_kwargs = kwargs.copy()
            new_kwargs.update({
                'phone': formatted_phone,
                'tenant': tenant,
            })

            exact_match = cls.objects.get(query)
            cls._update_instance(exact_match, new_kwargs)
            return exact_match

        except cls.DoesNotExist:

            new_kwargs = kwargs.copy()
            new_kwargs.update({
                'phone': formatted_phone,
                'tenant': tenant,
            })
        try:
            # If no match found, create a new contact
            return cls._create_instance(**new_kwargs)

        except Exception as e:
            print(f"Exception occurred: {e}")
            return None

    @classmethod
    def _create_instance(cls, **data):
        # Create a new instance of the class and save it directly
        instance = cls(**data)
        instance.save()  # This saves the instance to the database or storage
        return instance

    @classmethod
    def _update_instance(cls, instance, kwargs):
        """Helper method to update instance fields."""
        for key, value in kwargs.items():
            setattr(instance, key, value)
        instance.save()


class Company(TenantScopedModel):
    name = models.CharField(max_length=200, null=False)
    legal_name = models.CharField(max_length=200, null=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class Branch(TenantScopedModel):
    # Will be renamed as Place Branch will be a type of place

    name = models.CharField(max_length=200, null=False)
    address = models.CharField(max_length=400, null=False, blank=True)
    city = models.CharField(max_length=200, null=False, blank=True)
    state = models.CharField(max_length=200, null=False, blank=True)
    postal_code = models.CharField(max_length=40, null=False, blank=True)
    type = models.CharField(max_length=40, null=False, blank=True)
    category = models.CharField(max_length=40, null=False, blank=True)
    latitude = models.FloatField(null=True, blank=True, default=None)
    longitude = models.FloatField(null=True, blank=True, default=None)
    empresa = models.ForeignKey(Company, null=True, on_delete=models.SET_NULL)
    contacto = models.ForeignKey(Contact, null=True, on_delete=models.SET_NULL)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    geocoded = models.BooleanField(default=False)
    website = models.URLField(null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True)
    visibility = models.CharField(max_length=20, choices=VisibilityChoices.choices, default=VisibilityChoices.PUBLIC)

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"

    def __str__(self):
        return self.name


class Shipment(TenantScopedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    shipping_origin = models.CharField(max_length=40, null=True)
    shipping_code = models.CharField(max_length=40, null=True, unique=True)
    shipping_type = models.CharField(max_length=40, null=True)
    shipping_date = models.DateTimeField(null=True)
    shipping_invoice = models.CharField(max_length=40, null=True)
    shipping_condition = models.CharField(max_length=40, null=True)
    shipping_notes = models.TextField(max_length=360, null=True, blank=True)
    delivery_type = models.CharField(max_length=40, null=True)
    delivery_status = models.CharField(max_length=120, null=True)
    recipient_name = models.CharField(max_length=80, null=False)
    recipient_phone = models.CharField(max_length=40, null=True)
    recipient_email = models.CharField(max_length=250, null=True)
    closed = models.BooleanField(default=False)
    order = models.CharField(max_length=15, null=True, unique=True)
    tracking_code = models.CharField(max_length=140, null=True)
    creation_date = models.DateTimeField(auto_now_add=True, editable=False)
    closed_date = models.DateTimeField(null=True, blank=True)
    shipping_address = models.CharField(max_length=400, null=True, default="")
    comments = models.CharField(max_length=400, null=True, default="")

    class Meta:
        db_table = 'shipment'

    @property
    def duration(self):
        """
        Returns the time delta between creation_date and closed_date.
        If closed_date is None, calculates the delta up to the current time.
        """
        if self.closed_date:
            return self.closed_date - self.creation_date
        return timezone.now() - self.creation_date


class EcommerceOrderManager(models.Manager):

    def get_queryset(self):
        tenant = current_tenant.get()
        if tenant is None:
            return super().get_queryset()
        return super().get_queryset().filter(tenant=tenant)

    def search(self, search_word):
        return self.filter(
            Q(customer_name__icontains=search_word) |
            Q(customer_email__icontains=search_word) |
            Q(customer_phone__icontains=search_word) |
            Q(order_number__icontains=search_word), tenant=current_tenant.get()
        )


class EcommerceOrder(TenantScopedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    order_number = models.CharField(max_length=40, null=False)
    created = models.DateTimeField(null=True)
    status = models.CharField(max_length=40, null=False)
    customer_name = models.CharField(max_length=250, null=False)
    customer_phone = models.CharField(max_length=30, null=True)
    customer_email = models.CharField(max_length=250, null=True)
    order_customer_registered_address = models.TextField(default="")
    order_clean_delivery_address = models.TextField(default="", blank=True)
    payload = models.JSONField(default=dict)
    registered = models.DateTimeField(auto_now=True, editable=False)
    modified = models.DateTimeField(null=True)
    total = models.FloatField(default=0)
    tracking_code = models.CharField(max_length=100, blank=True, default="")

    objects = EcommerceOrderManager()

    class Meta:
        db_table = 'ecommerce_order'
        constraints = [
            models.UniqueConstraint(fields=['order_number', 'tenant'], name='unique_order_number_tenant')
        ]

    def __str__(self):
        return self.order_number


class EcommerceOrderLine(models.Model):
    order = models.ForeignKey(EcommerceOrder, on_delete=models.CASCADE, null=True)
    sku = models.CharField(max_length=40, null=False)
    quantity = models.IntegerField(default=0)
    price = models.FloatField(default=0)
    tax = models.FloatField(default=0)
    line_total = models.FloatField(default=0)

    def __str__(self):
        return f"{self.sku} - {self.quantity} - {self.line_total}"


class Ticket(TenantScopedModel):
    TICKET_STATUS_OPTIONS = [("O", "open"), ("A", "assigned"),("I", "in progress"), ("W", "waiting"), ("C", "closed"), ("P", "planned")]
    TICKET_TYPE_OPTIONS = [("I", "incident"), ("C", "change"), ("P", "planned")]

    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True)
    type = models.CharField(max_length=10, default="I", choices=TICKET_TYPE_OPTIONS)
    service = models.CharField(max_length=80, default="default")
    description = models.TextField(default="", blank=True)
    created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    creator = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, related_name='tickets_created')
    assigned = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, related_name='tickets_assigned')
    waiting_for = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, related_name='tickets_waiting_for')
    waiting_since = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, default="O", choices=TICKET_STATUS_OPTIONS)
    closed = models.DateTimeField(null=True, blank=True)
    target = models.DateTimeField(null=True, blank=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    origin_type = models.CharField(
        max_length=32,
        choices=TicketOriginChoices.choices,
        default=TicketOriginChoices.MANUAL,
        db_index=True
    )
    origin_ref = models.CharField(max_length=120, blank=True, default="")
    origin_session = models.ForeignKey(
        'chatbot.AgentSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets'
    )

    @classmethod
    def resolve_assignee(cls, value, tenant):
        """
        Resolve an assignee value to a Contact instance.
        
        Accepts:
        - None: returns None
        - Contact instance: returns as-is (validates tenant match if tenant provided)
        - User instance: looks up Contact by linked_user, falls back to email match
        - String (UUID): tries Contact.user_id first, then Contact.linked_user, then User.id lookup
        
        On any failure (invalid ID, no match, etc.), returns None (ticket saves unassigned).
        """
        from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
        from central_hub.models import MoioUser
        
        if value is None:
            return None
        
        if isinstance(value, Contact):
            if tenant is not None and value.tenant_id != tenant.id:
                return None
            return value
        
        if isinstance(value, MoioUser):
            contact = Contact.objects.filter(linked_user=value).first()
            if contact:
                if tenant is not None and contact.tenant_id != tenant.id:
                    return None
                return contact
            lookup_tenant = tenant if tenant is not None else value.tenant
            if lookup_tenant and value.email:
                return Contact.objects.filter(
                    tenant=lookup_tenant,
                    email__iexact=value.email
                ).first()
            return None
        
        if isinstance(value, str):
            contact_filter = {"user_id": value}
            if tenant is not None:
                contact_filter["tenant"] = tenant
            contact = Contact.objects.filter(**contact_filter).first()
            if contact:
                return contact
            
            try:
                user = MoioUser.objects.get(pk=value)
                contact = Contact.objects.filter(linked_user=user).first()
                if contact:
                    if tenant is not None and contact.tenant_id != tenant.id:
                        return None
                    return contact
                if tenant is not None and user.tenant_id != tenant.id:
                    return None
                lookup_tenant = tenant if tenant is not None else user.tenant
                if lookup_tenant and user.email:
                    return Contact.objects.filter(
                        tenant=lookup_tenant,
                        email__iexact=user.email
                    ).first()
                return None
            except (ObjectDoesNotExist, MultipleObjectsReturned, ValueError, TypeError):
                return None
        
        return None


class TicketComment(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True)
    ticket = models.ForeignKey(Ticket, related_name="comments", on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(default="", blank=True)
    creator = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True)


class CustomerMetadata(models.Model):
    label = models.CharField(max_length=100)
    value = models.CharField(max_length=300)


class Customer(TenantScopedModel):
    PERSON = 'Person'
    BUSINESS = 'Business'
    HOUSEHOLD = 'Household'

    CUSTOMER_TYPE_CHOICES = [
        (PERSON, 'Person'),
        (BUSINESS, 'Business'),
        (HOUSEHOLD, 'Household'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    type = models.CharField(max_length=50, choices=CUSTOMER_TYPE_CHOICES, default=PERSON)
    created = models.DateTimeField(auto_now_add=True)
    metadata = models.ForeignKey(CustomerMetadata, on_delete=models.CASCADE, null=True)
    legal_name = models.CharField(max_length=180, blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    first_name = models.CharField(max_length=100, null=True, default='')
    last_name = models.CharField(max_length=100, null=True, default='')
    date_of_birth = models.DateField(null=True, blank=True)
    national_document = models.CharField(max_length=40, blank=True, null=True)
    passport = models.CharField(max_length=40, blank=True, null=True)
    gender = models.CharField(max_length=40, blank=True, null=True)
    phone = models.CharField(max_length=40, null=True, unique=True)
    email = models.CharField(max_length=240, null=True, unique=True)
    external_id = models.CharField(max_length=80, null=True, unique=True)

    # CRM: contacts linked via CustomerContact (many-to-many)
    contacts = models.ManyToManyField(
        "Contact", through="CustomerContact", related_name="customers", blank=True
    )

    def __str__(self):
        return self.legal_name


class Address(models.Model):
    # Fields specific to a location
    customer = models.ForeignKey(Customer, related_name="address", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=200, blank=True, null=False)
    address_internal = models.CharField(max_length=200, blank=True, null=True)
    city = models.CharField(max_length=200, blank=True, null=True)
    state = models.CharField(max_length=200, blank=True, null=True)
    country = models.CharField(max_length=200, blank=True, null=True)
    postalcode = models.CharField(max_length=200, blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    type_location = models.CharField(max_length=40, blank=True, null=True)
    comments = models.CharField(max_length=200, blank=True, null=True)
    invoice_address = models.BooleanField(default=False)
    delivery_address = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    branch_code = models.CharField(max_length=40, blank=True, null=True, default=1)


class Tag(TenantScopedModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(default="", blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    context = models.CharField(max_length=150, null=True, blank=True)

    def save(self, *args, **kwargs):
        from central_hub.tenant_config import get_tenant_config
        config = get_tenant_config(self.tenant)
        mo = MoioOpenai(api_key=config.openai_api_key, default_model=config.openai_default_model)
        self.embedding = mo.get_embedding(f'{self.name} {self.description}', model=config.openai_embedding_model)
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

        constraints = [
            models.UniqueConstraint(
                fields=['tenant_id', 'name', 'context'],
                name='unique_tag_name_context_per_tenant'
            ),
            models.UniqueConstraint(
                fields=['tenant_id', 'slug', 'context'],
                name='unique_tag_slug_context_per_tenant'
            ),
        ]


class ProductManager(models.Manager):
    def search(self, search_word, tenant=None):
        if not tenant:
            tenant = current_tenant.get()

        return self.filter(
            Q(name__icontains=search_word) |
            Q(description__icontains=search_word) |
            Q(brand=search_word) |
            Q(category=search_word) |
            Q(sku=search_word), tenant=tenant
        )


class Product(TenantScopedModel):
    PRODUCT_TYPES = [
        ('STD', 'Standard'),
        ('VAR', 'Variable'),
        # You can add more types here in the future
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(default="", blank=True)
    price = models.FloatField(default=0)
    sale_price = models.FloatField(default=0)
    brand = models.CharField(max_length=100, blank=True, null=True)
    attributes = models.JSONField(default=dict)
    sku = models.CharField(max_length=40, blank=True, null=True)
    product_type = models.CharField(max_length=3, choices=PRODUCT_TYPES, default='STD')
    category = models.CharField(max_length=100, blank=True, null=True)
    tags = models.ManyToManyField(Tag, related_name='products', blank=True)
    price_currency = models.CharField(max_length=50, blank=True, null=True)
    permalink = models.URLField(blank=True, null=True)
    main_image = models.URLField(blank=True, null=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, null=False)
    fb_product_id = models.CharField(max_length=50, blank=True, null=True)
    frontend_product_id = models.CharField(max_length=50, blank=True, null=True)

    objects = ProductManager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from central_hub.tenant_config import get_tenant_config
        config = get_tenant_config(self.tenant)
        mo = MoioOpenai(api_key=config.openai_api_key, default_model=config.openai_default_model)

        self.embedding = mo.get_embedding(
            f'name:{self.name}, description:{self.description}, attributes:{self.attributes}',
            model=config.openai_embedding_model)
        self.slug = slugify(self.name)
        if self.fb_product_id is None and self.frontend_product_id is not None:
            self.fb_product_id = f"{self.sku.strip()}_{self.frontend_product_id}"

        super().save(*args, **kwargs)


class ProductVariant(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True)
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE,
                                limit_choices_to={'product_type': 'VAR'})
    sku = models.CharField(max_length=40, blank=True, null=True)
    variant_name = models.CharField(max_length=100)
    description = models.TextField(default="", blank=True)
    price = models.FloatField(default=0)
    sale_price = models.FloatField(default=0)

    def __str__(self):
        return f"{self.product.name} - {self.variant_name}"

    class Meta:
        unique_together = (("product", "variant_name"),)  # Ensures each variant name is unique per product

    def save(self, *args, **kwargs):
        # If the variant's price or sale_price is not set, inherit from the parent product
        if not self.price:
            self.price = self.product.price
        if not self.sale_price and self.product.sale_price:
            self.sale_price = self.product.sale_price
        super().save(*args, **kwargs)


class Stock(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True)
    sku = models.CharField(max_length=40, blank=True, null=True)
    quantity = models.IntegerField(default=0)

    def __str__(self):
        return f'sku: {self.sku} - quantity: {self.quantity}'


class WebhookConfig(TenantScopedModel):
    class AuthType(models.TextChoices):
        NONE = "none", _("No auth")
        BEARER_TOKEN = "bearer", _("Bearer / header token")
        BASIC = "basic", _("HTTP Basic user+pass")
        HMAC_SHA256 = "hmac", _("HMAC-SHA256 signature")
        CUSTOM_HEADER = "header", _("Static value in named header")
        QUERY_PARAM = "query", _("Static value in ?token=…")
        JWT = "jwt", _("JWT signed with HS256 / RS256")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, default="")

    # Validation rules
    expected_schema = models.TextField(blank=True, default="")  # JSONSchema string
    expected_content_type = models.CharField(max_length=60, blank=True, null=True)
    expected_origin = models.CharField(max_length=150, blank=True, null=True)
    store_payloads = models.BooleanField(default=True)

    # ⇢ AUTH ⇠
    auth_type = models.CharField(max_length=10, choices=AuthType.choices, default=AuthType.NONE)
    auth_config = models.JSONField(blank=True, default=dict)
    """
    Examples:
    • BEARER_TOKEN  → {"token": "my-shared-secret"}
    • BASIC         → {"username": "foo", "password": "bar"}
    • HMAC_SHA256   → {"secret": "raw-bytes-or-b64", "signature_header": "X-Sig"}
    • CUSTOM_HEADER → {"header": "X-Webhook-Key", "value": "abc123"}
    • QUERY_PARAM   → {"param": "token", "value": "abc123"}
    • JWT           → {"jwks_url": "..."} or {"secret": "…"} etc.
    """

    # ⇢ DISPATCH ⇠
    handler_path = models.CharField(  # python dotted path OR registry key
        max_length=255,
        blank=True,
        help_text="myapp.handlers.process_order or registry key",
    )

    url = models.URLField(blank=True, help_text="Exposed receive endpoint", null=True)
    locked = models.BooleanField(default=False)

    linked_flows = models.ManyToManyField(
        'flows.Flow',
        related_name='webhooks',
        blank=True,
        help_text="Flows that this webhook will trigger when called",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "webhook_config"

        # models.py (add this to WebhookConfig)

    def _check(self, request):
        """Return (True, None) on success, (False, reason_str) on failure."""
        t = self.auth_type

        if t == self.AuthType.NONE:
            return True, None

        if t == self.AuthType.BEARER_TOKEN:
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            return (token == self.auth_config.get("token"),
                    "Bearer token mismatch")

        if t == self.AuthType.BASIC:
            import base64
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Basic "):
                return False, "Missing Basic header"
            user, _, pwd = base64.b64decode(auth[6:]).decode().partition(":")
            ok = user == self.auth_config.get("username") and pwd == self.auth_config.get("password")
            return ok, "Invalid Basic credentials"

        if t == self.AuthType.CUSTOM_HEADER:
            hdr = self.auth_config.get("header")
            return (request.headers.get(hdr) == self.auth_config.get("value"),
                    f"Header {hdr} mismatch")

        if t == self.AuthType.QUERY_PARAM:
            pname = self.auth_config.get("param")
            return (request.query_params.get(pname) == self.auth_config.get("value"),
                    f"Query param {pname} mismatch")

        if t == self.AuthType.HMAC_SHA256:
            # 1) secret
            secret = self.auth_config.get("secret", "").encode()

            # 2) pull the full x-signature header (“ts=… ,v1=…”)
            sig_hdr = self.auth_config.get("signature_header", "x-signature").lower()
            x_signature = request.headers.get(sig_hdr, "")

            # 3) split out ts and v1
            ts = v1 = None
            for part in x_signature.split(","):
                if "=" not in part:
                    continue
                key, val = part.split("=", 1)
                if key.strip() == "ts":
                    ts = val.strip()
                elif key.strip() == "v1":
                    v1 = val.strip()

            # 4) pull the x-request-id
            request_id = request.headers.get("x-request-id", "")

            # 5) pull data.id from the querystring
            qs = request.META.get("QUERY_STRING", "")
            data_id = urllib.parse.parse_qs(qs).get("data.id", [""])[0]

            # 6) build the manifest exactly as they do
            manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"

            # 7) compute HMAC-SHA256 over that manifest
            calc_hash = hmac.new(secret, manifest.encode(), hashlib.sha256).hexdigest()

            # 8) constant-time compare
            ok = hmac.compare_digest(calc_hash, v1 or "")
            return ok, "HMAC signature mismatch"

        if t == self.AuthType.JWT:
            try:
                jwt_decode(
                    request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
                    key=self.auth_config.get("secret"),  # or supply key via jwks fetch
                    algorithms=["HS256", "RS256"],
                    audience=self.auth_config.get("aud"),
                )
                return True, None
            except InvalidTokenError as e:
                return False, str(e)

        return False, "Unknown auth type"


class WebhookPayload(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True)
    config = models.ForeignKey(WebhookConfig, related_name="payloads", on_delete=models.SET_NULL, null=True, blank=True)
    payload = models.JSONField(default=dict, null=True, blank=True)
    status = models.CharField(max_length=100, blank=True, null=True, default="received")


class KnowledgeItem(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True)
    title = models.CharField(max_length=150, unique=True)
    description = models.TextField(default="", blank=True)
    url = models.URLField(null=True, blank=True)
    type = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=150, blank=True, null=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    visibility = models.CharField(max_length=20, choices=VisibilityChoices.choices, default=VisibilityChoices.PUBLIC)
    slug = models.SlugField(max_length=150, null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, null=True)
    modified = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):

        from central_hub.tenant_config import get_tenant_config
        config = get_tenant_config(self.tenant)
        mo = MoioOpenai(api_key=config.openai_api_key, default_model=config.openai_default_model)

        self.embedding = mo.get_embedding(
            f'title:{self.title}, description:{self.description},  category:{self.category}',
            model=config.openai_embedding_model)
        super().save(*args, **kwargs)

    def update(self, **kwargs):

        """
        Update a Django ORM instance dynamically, warning if extra fields are ignored.

        :param instance: A Django model instance
        :param kwargs: Key-value pairs of fields to update
        :return: Tuple (updated_instance, warning_message) where warning_message is None if no extra fields were found.
        """
        # Get valid model field names
        valid_fields = {field.name for field in self._meta.get_fields()}

        # Identify invalid (extra) fields
        extra_fields = set(kwargs.keys()) - valid_fields
        warning_message = None

        if extra_fields:
            warning_message = f"Warning: These fields were ignored as they do not exist: {', '.join(extra_fields)}"
            print(warning_message)  # Optional: Log it instead of printing

        # Update only valid fields
        for key, value in kwargs.items():
            if key in valid_fields:
                setattr(self, key, value)

        self.save()  # Save changes to the database
        return self, warning_message


UserModel = get_user_model()


class CustomerContact(TenantScopedModel):
    """
    Relation table between Customer and Contact.
    Supports multiple customers per contact (e.g. household + company),
    with roles and current/historical validity.
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="customer_contacts")
    contact = models.ForeignKey("Contact", on_delete=models.CASCADE, related_name="customer_contacts")
    role = models.CharField(max_length=100, blank=True)  # CEO, Purchasing, Head of household, etc.
    is_primary = models.BooleanField(default=False)
    is_billing = models.BooleanField(default=False)
    is_decision_maker = models.BooleanField(default=False)

    # Relation validity
    is_current = models.BooleanField(default=True)  # True = relation is active
    started_at = models.DateTimeField(null=True, blank=True)  # When relation began
    ended_at = models.DateTimeField(null=True, blank=True)  # When relation ended; null if still current

    def __str__(self):
        return f"{self.contact.fullname} - {self.customer.name} ({self.role})"

    class Meta:
        db_table = "crm_customer_contact"
        unique_together = ["customer", "contact"]  # One relation per customer-contact pair


class ActivityTypeCategory(models.TextChoices):
    COMMUNICATION = "communication", _("Communication")
    MEETING = "meeting", _("Meeting")
    VISIT = "visit", _("Visit")
    PROPOSAL = "proposal", _("Proposal")
    TASK = "task", _("Task")
    OTHER = "other", _("Other")


class ActivityType(TenantScopedModel):
    """Tenant-configurable catalog of activity semantics."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, default="Generic", blank=True)
    key = models.CharField(max_length=60)
    label = models.CharField(max_length=150)
    category = models.CharField(
        max_length=40,
        choices=ActivityTypeCategory.choices,
        default=ActivityTypeCategory.OTHER,
    )
    schema = models.JSONField(null=True, blank=True)
    default_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    default_visibility = models.CharField(
        max_length=20,
        choices=VisibilityChoices.choices,
        default=VisibilityChoices.PUBLIC,
    )
    default_status = models.CharField(max_length=20, default="completed")
    sla_days = models.PositiveIntegerField(null=True, blank=True)
    icon = models.CharField(max_length=40, blank=True, default="")
    color = models.CharField(max_length=20, blank=True, default="")
    requires_contact = models.BooleanField(default=False)
    requires_deal = models.BooleanField(default=False)
    title_template = models.CharField(max_length=200, blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.label or self.key

    class Meta:
        ordering = ["order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key"],
                name="unique_activity_type_key_per_tenant",
            )
        ]


class ActivityKind(models.TextChoices):
    NOTE = "note", "Note"
    TASK = "task", "Task"
    IDEA = "idea", "Idea"
    EVENT = "event", "Event"
    OTHER = "other", "Other"


class ActivityStatus(models.TextChoices):
    PLANNED = "planned", _("Planned")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    EXPIRED = "expired", _("Expired")


class ActivitySourceChoices(models.TextChoices):
    MANUAL = "manual", _("Manual")
    SYSTEM = "system", _("System")
    SUGGESTION = "suggestion", _("Suggestion")


class ActivityRecord(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(default=timezone.now, null=False)
    title = models.CharField(max_length=255, default="No Title", blank=True)
    content = models.JSONField(default=dict, null=True, blank=True)
    user = models.ForeignKey(
        UserModel,
        related_name="activity_records",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    source = models.CharField(
        max_length=20,
        choices=ActivitySourceChoices.choices,
        default=ActivitySourceChoices.MANUAL,
        blank=True,
    )
    visibility = models.CharField(
        max_length=20,
        choices=VisibilityChoices.choices,
        default=VisibilityChoices.PUBLIC,
    )
    type = models.ForeignKey(
        ActivityType,
        related_name="activity_records",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        default=None,
    )
    kind = models.CharField(
        max_length=20,
        choices=ActivityKind.choices,
        default=ActivityKind.NOTE,
    )
    status = models.CharField(
        max_length=20,
        choices=ActivityStatus.choices,
        default=ActivityStatus.COMPLETED,
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    owner = models.ForeignKey(
        UserModel,
        related_name="activity_records_owned",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        UserModel,
        related_name="activity_records_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    deal = models.ForeignKey(
        "Deal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    tags = models.JSONField(default=list, blank=True)
    reason = models.CharField(max_length=200, blank=True, default="")
    needs_confirmation = models.BooleanField(default=False)
    # Backtrace to immutable capture entry (optional; added by Anchored Activity Capture)
    originating_capture_entry = models.ForeignKey(
        "ActivityCaptureEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_activity_records",
    )

    def __str__(self):
        return f"{self.kind.capitalize()}: {self.title}"

    class Meta:
        indexes = [
            models.Index(fields=["kind"]),
            models.Index(fields=["type"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["scheduled_at"]),
            models.Index(fields=["contact"]),
            models.Index(fields=["owner"]),
        ]


class ActivitySuggestionStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    ACCEPTED = "accepted", _("Accepted")
    DISMISSED = "dismissed", _("Dismissed")


class ActivitySuggestion(TenantScopedModel):
    """System-generated suggestion that can be accepted to create an ActivityRecord."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_key = models.CharField(max_length=60)
    reason = models.CharField(max_length=200)
    confidence = models.FloatField(null=True, blank=True)
    suggested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    proposed_fields = models.JSONField(default=dict, blank=True)
    target_contact_id = models.CharField(max_length=100, null=True, blank=True)
    target_customer_id = models.UUIDField(null=True, blank=True)
    target_deal_id = models.UUIDField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        UserModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_suggestions",
    )
    status = models.CharField(
        max_length=20,
        choices=ActivitySuggestionStatus.choices,
        default=ActivitySuggestionStatus.PENDING,
    )
    activity_record = models.OneToOneField(
        ActivityRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggestion_origin",
    )
    created_by_source = models.CharField(max_length=60)
    # Optional link to an anchored capture entry that spawned this suggestion.
    capture_entry = models.ForeignKey(
        "ActivityCaptureEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suggestions",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["assigned_to"]),
            models.Index(fields=["suggested_at"]),
        ]


# ===============================================================================
# Anchored Activity Capture (immutable source-of-truth)
# ===============================================================================


class CaptureStatus(models.TextChoices):
    CAPTURED = "captured", _("Captured")
    CLASSIFYING = "classifying", _("Classifying")
    CLASSIFIED = "classified", _("Classified")
    NEEDS_REVIEW = "needs_review", _("Needs Review")
    REVIEWED = "reviewed", _("Reviewed")
    APPLYING = "applying", _("Applying")
    APPLIED = "applied", _("Applied")
    FAILED = "failed", _("Failed")


class CaptureRawSource(models.TextChoices):
    MANUAL_TEXT = "manual_text", _("Manual Text")
    VOICE_TRANSCRIPT = "voice_transcript", _("Voice Transcript")
    IMPORT = "import", _("Import")
    AUTOMATION = "automation", _("Automation")


class CaptureAnchorModel(models.TextChoices):
    DEAL = "crm.deal", _("Deal")
    CONTACT = "crm.contact", _("Contact")
    CUSTOMER = "crm.customer", _("Customer")


class ActivityCaptureEntry(TenantScopedModel):
    """
    Immutable capture entry representing raw human intent.

    Adaptation notes:
    - `anchor_id` is stored as a string to support Contact.user_id (string PK) and UUID PKs.
    - `visibility` reuses `crm.models.VisibilityChoices` to match existing ActivityRecord semantics.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Anchor (required)
    anchor_model = models.CharField(max_length=50, choices=CaptureAnchorModel.choices)
    anchor_id = models.CharField(max_length=100, db_index=True)

    actor = models.ForeignKey(
        UserModel,
        on_delete=models.PROTECT,
        related_name="activity_captures",
    )

    # Immutable raw input
    raw_text = models.TextField()
    raw_source = models.CharField(
        max_length=30,
        choices=CaptureRawSource.choices,
        default=CaptureRawSource.MANUAL_TEXT,
    )
    channel_hint = models.CharField(max_length=30, null=True, blank=True)

    # Visibility & RBAC
    visibility = models.CharField(
        max_length=20,
        choices=VisibilityChoices.choices,
        default=VisibilityChoices.INTERNAL,
    )
    allowed_roles = models.ManyToManyField("auth.Group", blank=True)
    allowed_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")

    # Lifecycle
    status = models.CharField(
        max_length=30,
        choices=CaptureStatus.choices,
        default=CaptureStatus.CAPTURED,
        db_index=True,
    )

    # LLM classification (structured)
    llm_model = models.CharField(max_length=100, blank=True, default="gpt-4o-mini")
    prompt_version = models.CharField(max_length=20, blank=True, default="v2.0")
    raw_llm_response = models.JSONField(null=True, blank=True)
    classification = models.JSONField(null=True, blank=True)
    suggested_activities = models.JSONField(null=True, blank=True, default=list)
    summary = models.TextField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    review_reasons = models.JSONField(default=list, blank=True)
    error_details = models.JSONField(null=True, blank=True)

    # Final state after review
    final = models.JSONField(null=True, blank=True)
    processed_at = models.DateTimeField(auto_now=True)

    # Applied canonical objects
    applied_refs = models.JSONField(null=True, blank=True)

    # Idempotency
    idempotency_key = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "anchor_model", "anchor_id", "-created_at"]),
            models.Index(fields=["tenant", "actor", "-created_at"]),
            models.Index(fields=["tenant", "status", "updated_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_capture_idempotency_per_tenant",
            )
        ]


class CaptureEntryLink(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(ActivityCaptureEntry, on_delete=models.CASCADE, related_name="extra_links")
    ref_model = models.CharField(max_length=50)
    ref_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "ref_model", "ref_id"]),
            models.Index(fields=["tenant", "entry", "created_at"]),
        ]


class CaptureEntryAuditEvent(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(ActivityCaptureEntry, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=50)
    event_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "entry", "-created_at"]),
            models.Index(fields=["tenant", "event_type", "-created_at"]),
        ]


# ========FACES ==================================================================


class Face(TenantScopedModel):  # <- your tenant mix-in
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to="faces/")  # stored still frame
    embedding = VectorField(dimensions=128, null=True, blank=True, editable=False)  # match your encoder
    seen = models.PositiveIntegerField(default=1)
    last_seen = models.DateTimeField(default=timezone.now)
    created = models.DateTimeField(auto_now_add=True)
    contact = models.ForeignKey(
        "Contact",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="faces",
    )

    class Meta:
        ordering = ["-last_seen"]
        indexes = [
            models.Index(fields=["last_seen"]),
            models.Index(fields=["contact"]),
            # No vector index here → migrations will succeed everywhere
        ]

    def __str__(self) -> str:
        return str(self.id)


class FaceDetection(TenantScopedModel):  # <- your tenant mix-in
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to="faces/")  # stored still frame
    embedding = VectorField(dimensions=128, null=True, blank=True)  # match your encoder
    created = models.DateTimeField(auto_now_add=True)
    face = models.ForeignKey(Face, related_name="detections", on_delete=models.CASCADE, null=True,)
    distance = models.FloatField(null=True, blank=True)

    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created"]


    def __str__(self) -> str:
        return str(self.id)


# ======== DEALS / OPPORTUNITIES ================================================


class DealPriorityChoices(models.TextChoices):
    LOW = 'low', _('Low')
    MEDIUM = 'medium', _('Medium')
    HIGH = 'high', _('High')
    URGENT = 'urgent', _('Urgent')


class DealStatusChoices(models.TextChoices):
    OPEN = 'open', _('Open')
    WON = 'won', _('Won')
    LOST = 'lost', _('Lost')


class Pipeline(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Pipeline')
        verbose_name_plural = _('Pipelines')
        ordering = ['-is_default', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_pipeline_name_per_tenant'
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            Pipeline.objects.filter(tenant=self.tenant, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class PipelineStage(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='stages')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    probability = models.PositiveIntegerField(default=0, help_text=_("Win probability percentage (0-100)"))
    is_won_stage = models.BooleanField(default=False)
    is_lost_stage = models.BooleanField(default=False)
    color = models.CharField(max_length=20, blank=True, default="#6366f1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Pipeline Stage')
        verbose_name_plural = _('Pipeline Stages')
        ordering = ['pipeline', 'order']
        constraints = [
            models.UniqueConstraint(
                fields=['pipeline', 'name'],
                name='unique_stage_name_per_pipeline'
            )
        ]

    def __str__(self):
        return f"{self.pipeline.name} - {self.name}"


class DealManager(models.Manager):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)

    def open_deals(self, tenant):
        return self.filter(tenant=tenant, status=DealStatusChoices.OPEN)

    def won_deals(self, tenant):
        return self.filter(tenant=tenant, status=DealStatusChoices.WON)

    def lost_deals(self, tenant):
        return self.filter(tenant=tenant, status=DealStatusChoices.LOST)


class Deal(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals'
    )
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals'
    )
    stage = models.ForeignKey(
        PipelineStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals'
    )

    value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")

    probability = models.PositiveIntegerField(
        default=0,
        help_text=_("Win probability percentage (0-100)")
    )
    priority = models.CharField(
        max_length=20,
        choices=DealPriorityChoices.choices,
        default=DealPriorityChoices.MEDIUM
    )
    status = models.CharField(
        max_length=20,
        choices=DealStatusChoices.choices,
        default=DealStatusChoices.OPEN
    )

    expected_close_date = models.DateField(null=True, blank=True)
    actual_close_date = models.DateField(null=True, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_deals'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals_created'
    )

    won_reason = models.TextField(blank=True, default="")
    lost_reason = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)
    comments = models.JSONField(default=list, blank=True, help_text=_("List of comments on the deal"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DealManager()

    class Meta:
        verbose_name = _('Deal')
        verbose_name_plural = _('Deals')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['expected_close_date']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.stage:
            self.probability = self.stage.probability
            if self.stage.is_won_stage:
                self.status = DealStatusChoices.WON
                if not self.actual_close_date:
                    self.actual_close_date = timezone.now().date()
            elif self.stage.is_lost_stage:
                self.status = DealStatusChoices.LOST
                if not self.actual_close_date:
                    self.actual_close_date = timezone.now().date()
        super().save(*args, **kwargs)

    @property
    def weighted_value(self):
        if self.value is None or self.probability is None:
            return None
        return self.value * Decimal(self.probability) / Decimal(100)

    def add_comment(self, text: str, author=None, comment_type: str = "general", 
                    from_stage: str = None, to_stage: str = None) -> dict:
        import uuid as uuid_module
        author_name = None
        if author:
            author_name = f"{author.first_name} {author.last_name}".strip() or author.email
        comment = {
            "id": str(uuid_module.uuid4()),
            "text": text,
            "type": comment_type,
            "author_id": str(author.id) if author else None,
            "author_name": author_name,
            "created_at": timezone.now().isoformat(),
        }
        if comment_type == "stage_change":
            comment["from_stage"] = from_stage
            comment["to_stage"] = to_stage
        
        if not isinstance(self.comments, list):
            self.comments = []
        self.comments.append(comment)
        return comment


# Shopify sync models (tenant-scoped; migrations in crm so they run on tenant schemas only)
from crm.shopify_sync_models import (  # noqa: E402
    ShopifyCustomer,
    ShopifyOrder,
    ShopifyProduct,
    ShopifySyncLog,
)
