import logging
import re

from crm.models import Contact, ContactType, ContactTypeChoices
import logging
import phonenumbers
from phonenumbers import carrier, parse, NumberParseException, format_number
from django.db.models import Q
from central_hub.models import TenantConfiguration
from chatbot.lib.whatsapp_client_api import WhatsappBusinessClient
logger = logging.getLogger(__name__)

_NON_DIALABLE_RE = re.compile(r"[^\d+]+")


def normalize_phone_e164(raw_phone: str | None) -> str | None:
    """
    Best-effort phone normalization to E.164.

    Accepts:
      - "+549112233..." (already prefixed)
      - "549112233..." (WhatsApp wa_id style)
      - "00..." (international prefix) -> "+..."
      - strings with spaces/dashes/parentheses
    """
    if not raw_phone:
        return None
    phone = str(raw_phone).strip()
    if not phone:
        return None

    # Keep digits and '+' only (remove spaces, dashes, etc.)
    phone = _NON_DIALABLE_RE.sub("", phone)
    if phone.startswith("00"):
        phone = f"+{phone[2:]}"
    if phone and not phone.startswith("+") and phone.isdigit():
        phone = f"+{phone}"

    try:
        parsed = parse(phone)
        return format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        return None


def _candidate_phone_values(raw_phone: str | None) -> list[str]:
    """
    Generate a small set of plausible stored representations for a phone number.
    This helps match legacy/unnormalized `Contact.phone` values.
    """
    if not raw_phone:
        return []
    raw = str(raw_phone).strip()
    if not raw:
        return []

    cleaned = _NON_DIALABLE_RE.sub("", raw)
    candidates = {raw, cleaned}
    if cleaned.startswith("00"):
        candidates.add(f"+{cleaned[2:]}")
    if cleaned and cleaned.isdigit():
        candidates.add(f"+{cleaned}")
    if raw and raw.isdigit():
        candidates.add(f"+{raw}")

    normalized = normalize_phone_e164(raw)
    if normalized:
        candidates.add(normalized)
        candidates.add(normalized.lstrip("+"))

    # Remove empties and keep stable order
    result: list[str] = []
    for item in candidates:
        item = str(item).strip()
        if item and item not in result:
            result.append(item)
    return result


def get_contact_by_phone(phone, whatsapp_name, config: TenantConfiguration):

    formatted_phone = normalize_phone_e164(phone) or str(phone).strip()
    print(f'formatted_number: {formatted_phone}')

    try:

        contact = Contact.objects.get(phone=formatted_phone, tenant=config.tenant)
        logger.info("Contact found: %s %s", formatted_phone, whatsapp_name)
        if contact.whatsapp_name != whatsapp_name:
            contact.whatsapp_name = whatsapp_name
            contact.save()

    except Contact.DoesNotExist:
        logger.warning("Creating Contact: %s %s", formatted_phone, whatsapp_name)
        contact = Contact.objects.create(phone=formatted_phone,
                                         whatsapp_name=whatsapp_name,
                                         tenant=config.tenant,
                                         source="chatbot")
        contact.save()
    except Contact.MultipleObjectsReturned:
        # If duplicates exist, pick the most recently updated record.
        contact = (
            Contact.objects.filter(phone=formatted_phone, tenant=config.tenant)
            .order_by("-updated")
            .first()
        )
        logger.error("Multiple Contacts Found: %s %s", formatted_phone, whatsapp_name)

    if contact is None:
        # Extremely defensive fallback (shouldn't happen, but avoids crashing message processing).
        contact = Contact.objects.create(
            phone=formatted_phone,
            whatsapp_name=whatsapp_name,
            tenant=config.tenant,
            source="chatbot",
        )

    if contact.ctype is None:
        try:
            rol = ContactType.objects.get(name=ContactTypeChoices.LEAD, tenant=config.tenant)
            contact.ctype = rol
            contact.save()

        except ContactType.DoesNotExist:

            rol = ContactType.objects.create(name=ContactTypeChoices.LEAD, tenant=config.tenant)
            rol.save()
            contact.ctype = rol
            contact.save()

    return contact


def is_blacklisted_contact(phone, tenant) -> bool:
    candidates = _candidate_phone_values(phone)
    if not candidates:
        return False

    # Match against phone/mobile/alt_phone to handle legacy storage patterns.
    return Contact.objects.filter(tenant=tenant, is_blacklisted=True).filter(
        Q(phone__in=candidates) | Q(mobile__in=candidates) | Q(alt_phone__in=candidates)
    ).exists()



def sync_whatsapp_blocklist(contact: Contact, *, enabled: bool) -> None:
    if not contact.phone:
        return

    config = TenantConfiguration.objects.filter(
        tenant=contact.tenant,
        whatsapp_integration_enabled=True,
    ).first()
    if not config:
        return

    try:
        client = WhatsappBusinessClient(config)
    except Exception:
        logger.exception("Failed to initialize WhatsApp client for blocklist sync")
        return

    users = [contact.phone]
    result = client.block_users(users) if enabled else client.unblock_users(users)
    if not result.get("success"):
        logger.error("WhatsApp blocklist sync failed: %s", result.get("error"))

