from __future__ import annotations

from typing import Optional, Tuple

import phonenumbers
from django.utils import timezone

from chatbot.models.chatbot_session import ChatbotSession
from crm.models import Contact, ContactType, ContactTypeChoices
from portal.models import Tenant

from . import models


def _default_contact_type(tenant: Tenant) -> ContactType:
    contact_type, _ = ContactType.objects.get_or_create(
        tenant=tenant,
        name=ContactTypeChoices.LEAD,
    )
    return contact_type


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    value = phone.strip()
    if not value:
        return None
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException:
        return value
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def ensure_session_contact(
    session: Optional[models.VisitorSession],
    tenant: Optional[Tenant],
) -> Optional[Contact]:
    if session is None or tenant is None:
        return None
    if session.contact_id:
        return session.contact

    defaults = {
        "tenant": tenant,
        "fullname": "",
        "source": "webchat",
        "ctype": _default_contact_type(tenant),
    }
    contact, _ = Contact.objects.get_or_create(
        user_id=str(session.id),
        defaults=defaults,
    )

    updates = []
    if contact.tenant_id != tenant.id:
        contact.tenant = tenant
        updates.append("tenant")
    if contact.ctype_id is None:
        contact.ctype = defaults["ctype"]
        updates.append("ctype")
    if contact.source != "webchat":
        contact.source = "webchat"
        updates.append("source")
    if updates:
        contact.save(update_fields=updates + ["updated"])

    session.contact = contact
    session.save(update_fields=["contact", "updated_at"])
    return contact


def ensure_webchat_session(
    session: Optional[models.VisitorSession],
    tenant: Optional[Tenant],
) -> Tuple[Optional[Contact], Optional[ChatbotSession]]:
    contact = ensure_session_contact(session, tenant)
    if session is None or contact is None:
        return contact, None

    defaults = {
        "tenant": tenant,
        "contact": contact,
        "start": timezone.now(),
        "last_interaction": timezone.now(),
        "channel": "webchat",
        "started_by": "webchat",
    }
    chatbot_session, created = ChatbotSession.objects.get_or_create(
        session=str(session.id),
        defaults=defaults,
    )

    updates = []
    if chatbot_session.contact_id != contact.user_id:
        chatbot_session.contact = contact
        updates.append("contact")
    if chatbot_session.tenant_id != tenant.id:
        chatbot_session.tenant = tenant
        updates.append("tenant")
    if chatbot_session.channel != "webchat":
        chatbot_session.channel = "webchat"
        updates.append("channel")
    if updates:
        chatbot_session.save(update_fields=updates)

    if created and not chatbot_session.context:
        chatbot_session.context = [{"role": "system", "content": "webchat session"}]
        chatbot_session.save(update_fields=["context"])

    return contact, chatbot_session


def resolve_session_contact(
    session: Optional[models.VisitorSession],
    tenant: Optional[Tenant],
) -> Optional[Contact]:
    if session is None:
        return None
    if session.contact_id:
        return session.contact
    return ensure_session_contact(session, tenant)


def _find_existing_contact(
    *,
    tenant: Optional[Tenant],
    email: Optional[str],
    phone: Optional[str],
    exclude_user_id: Optional[str],
) -> Optional[Contact]:
    if tenant is None:
        return None

    candidate: Optional[Contact] = None
    if email:
        queryset = Contact.objects.filter(tenant=tenant, email__iexact=email)
        if exclude_user_id:
            queryset = queryset.exclude(user_id=exclude_user_id)
        candidate = queryset.first()

    if candidate is None and phone:
        queryset = Contact.objects.filter(tenant=tenant, phone=phone)
        if exclude_user_id:
            queryset = queryset.exclude(user_id=exclude_user_id)
        candidate = queryset.first()

    return candidate


def _bind_session_to_contact(
    session: Optional[models.VisitorSession], contact: Contact
) -> None:
    if session is None:
        return
    if session.contact_id == contact.user_id:
        return
    session.contact = contact
    session.save(update_fields=["contact", "updated_at"])
    ChatbotSession.objects.filter(session=str(session.id)).update(contact=contact)


def update_contact_profile(
    contact: Optional[Contact],
    *,
    session: Optional[models.VisitorSession] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[Contact]:
    if contact is None:
        return None

    trimmed_email = email.strip() if email and email.strip() else None
    normalized_phone = _normalize_phone(phone)

    existing = _find_existing_contact(
        tenant=getattr(contact, "tenant", None),
        email=trimmed_email,
        phone=normalized_phone,
        exclude_user_id=contact.user_id,
    )
    if existing:
        contact = existing
        _bind_session_to_contact(session, contact)

    updates = []
    if trimmed_email and trimmed_email != (contact.email or ""):
        contact.email = trimmed_email
        updates.append("email")
    if normalized_phone and normalized_phone != (contact.phone or ""):
        contact.phone = normalized_phone
        updates.append("phone")
    if name and name.strip() and name.strip() != (contact.fullname or ""):
        contact.fullname = name.strip()
        updates.append("fullname")
        if not contact.display_name:
            contact.display_name = contact.fullname
            updates.append("display_name")
    if updates:
        contact.save(update_fields=updates + ["updated"])
    return contact


def record_topic_interest(contact: Optional[Contact], topic: Optional[models.Topic]) -> None:
    if contact is None or topic is None:
        return
    traits = contact.traits or {}
    interests = list(traits.get("interests", []))
    if any(entry.get("slug") == topic.slug for entry in interests):
        return
    interests.append({"slug": topic.slug, "title": topic.title})
    traits["interests"] = interests
    contact.traits = traits
    contact.save(update_fields=["traits", "updated"])


# ---------------------------------------------------------------------------
# Bundle Validation Service
# ---------------------------------------------------------------------------

import re
from dataclasses import dataclass, field
from typing import Any

DANGEROUS_PATTERNS = [
    re.compile(r'<script\b', re.IGNORECASE),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),
    re.compile(r'eval\s*\(', re.IGNORECASE),
    re.compile(r'Function\s*\(', re.IGNORECASE),
    re.compile(r'document\s*\.', re.IGNORECASE),
    re.compile(r'window\s*\.', re.IGNORECASE),
    re.compile(r'import\s*\(', re.IGNORECASE),
    re.compile(r'require\s*\(', re.IGNORECASE),
    re.compile(r'data:\s*text/html', re.IGNORECASE),
    re.compile(r'vbscript:', re.IGNORECASE),
]

ALLOWED_SLOT_TYPES = {
    'text', 'textarea', 'richtext', 'markdown',
    'number', 'boolean', 'url', 'email', 'phone',
    'image', 'video', 'file', 'media',
    'select', 'multiselect', 'radio', 'checkbox',
    'date', 'datetime', 'time',
    'color', 'json', 'array', 'object',
    'reference', 'content_reference',
}


@dataclass
class ValidationResult:
    """Result of bundle validation."""
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.is_valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: 'ValidationResult') -> None:
        if not other.is_valid:
            self.is_valid = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def to_dict(self) -> dict:
        return {
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
        }


class BundleValidationService:
    """
    Validates block bundle definitions for correctness and security.
    """

    def validate_bundle_version(self, bundle_version) -> ValidationResult:
        """
        Validate a complete bundle version including all block definitions.
        """
        result = ValidationResult()

        if not bundle_version.manifest:
            result.add_warning("Bundle version has no manifest")

        for block_def in bundle_version.block_definitions.all():
            block_result = self.validate_block_definition(block_def)
            result.merge(block_result)

        return result

    def validate_block_definition(self, block_def) -> ValidationResult:
        """
        Validate a single block definition.
        """
        result = ValidationResult()
        prefix = f"Block '{block_def.block_type_id}': "

        if not block_def.block_type_id:
            result.add_error(f"{prefix}block_type_id is required")
        elif not re.match(r'^[a-z][a-z0-9-]*$', block_def.block_type_id):
            result.add_error(f"{prefix}block_type_id must be lowercase alphanumeric with hyphens")

        if not block_def.name:
            result.add_error(f"{prefix}name is required")

        result.merge(self.validate_variants(block_def.variants, prefix))
        result.merge(self.validate_toggles(block_def.feature_toggles, prefix))
        result.merge(self.validate_style_axes(block_def.style_axes, prefix))
        result.merge(self.validate_content_slots(block_def.content_slots, prefix))
        result.merge(self.validate_defaults(block_def.defaults, block_def, prefix))

        if block_def.preview_template:
            security_result = self.check_security(block_def.preview_template, f"{prefix}preview_template")
            result.merge(security_result)

        return result

    def validate_variants(self, variants: list, prefix: str = "") -> ValidationResult:
        """Validate variant definitions."""
        result = ValidationResult()

        if not isinstance(variants, list):
            result.add_error(f"{prefix}variants must be an array")
            return result

        seen_ids = set()
        for i, variant in enumerate(variants):
            var_prefix = f"{prefix}variants[{i}]: "

            if not isinstance(variant, dict):
                result.add_error(f"{var_prefix}must be an object")
                continue

            variant_id = variant.get('id')
            if not variant_id:
                result.add_error(f"{var_prefix}'id' is required")
            elif variant_id in seen_ids:
                result.add_error(f"{var_prefix}duplicate variant id '{variant_id}'")
            else:
                seen_ids.add(variant_id)

            if not variant.get('name'):
                result.add_warning(f"{var_prefix}'name' is recommended for editor display")

            result.merge(self.check_security(variant, f"{prefix}variants[{i}]"))

        return result

    def validate_toggles(self, toggles: list, prefix: str = "") -> ValidationResult:
        """Validate toggle definitions."""
        result = ValidationResult()

        if not isinstance(toggles, list):
            result.add_error(f"{prefix}feature_toggles must be an array")
            return result

        seen_ids = set()
        for i, toggle in enumerate(toggles):
            toggle_prefix = f"{prefix}feature_toggles[{i}]: "

            if not isinstance(toggle, dict):
                result.add_error(f"{toggle_prefix}must be an object")
                continue

            toggle_id = toggle.get('id')
            if not toggle_id:
                result.add_error(f"{toggle_prefix}'id' is required")
            elif toggle_id in seen_ids:
                result.add_error(f"{toggle_prefix}duplicate toggle id '{toggle_id}'")
            else:
                seen_ids.add(toggle_id)

            if not toggle.get('name'):
                result.add_warning(f"{toggle_prefix}'name' is recommended for editor display")

            default_val = toggle.get('default')
            if default_val is not None and not isinstance(default_val, bool):
                result.add_error(f"{toggle_prefix}'default' must be a boolean")

        return result

    def validate_style_axes(self, style_axes: dict, prefix: str = "") -> ValidationResult:
        """Validate style axis definitions."""
        result = ValidationResult()

        if not isinstance(style_axes, dict):
            result.add_error(f"{prefix}style_axes must be an object")
            return result

        for axis_name, options in style_axes.items():
            axis_prefix = f"{prefix}style_axes.{axis_name}: "

            if not isinstance(options, list):
                result.add_error(f"{axis_prefix}options must be an array")
                continue

            if len(options) == 0:
                result.add_warning(f"{axis_prefix}axis has no options defined")

            seen_options = set()
            for opt in options:
                if not isinstance(opt, str):
                    result.add_error(f"{axis_prefix}all options must be strings")
                    break
                if opt in seen_options:
                    result.add_error(f"{axis_prefix}duplicate option '{opt}'")
                seen_options.add(opt)

        return result

    def validate_content_slots(self, slots: list, prefix: str = "") -> ValidationResult:
        """Validate content slot schema definitions."""
        result = ValidationResult()

        if not isinstance(slots, list):
            result.add_error(f"{prefix}content_slots must be an array")
            return result

        seen_ids = set()
        for i, slot in enumerate(slots):
            slot_prefix = f"{prefix}content_slots[{i}]: "

            if not isinstance(slot, dict):
                result.add_error(f"{slot_prefix}must be an object")
                continue

            slot_id = slot.get('id')
            if not slot_id:
                result.add_error(f"{slot_prefix}'id' is required")
            elif slot_id in seen_ids:
                result.add_error(f"{slot_prefix}duplicate slot id '{slot_id}'")
            else:
                seen_ids.add(slot_id)

            slot_type = slot.get('type', 'text')
            if slot_type not in ALLOWED_SLOT_TYPES:
                result.add_error(f"{slot_prefix}invalid type '{slot_type}'. Allowed: {', '.join(sorted(ALLOWED_SLOT_TYPES))}")

            if 'required' in slot and not isinstance(slot['required'], bool):
                result.add_error(f"{slot_prefix}'required' must be a boolean")

            if 'max_length' in slot:
                if not isinstance(slot['max_length'], int) or slot['max_length'] <= 0:
                    result.add_error(f"{slot_prefix}'max_length' must be a positive integer")

            if 'min_length' in slot:
                if not isinstance(slot['min_length'], int) or slot['min_length'] < 0:
                    result.add_error(f"{slot_prefix}'min_length' must be a non-negative integer")

            if 'min_length' in slot and 'max_length' in slot:
                if slot['min_length'] > slot['max_length']:
                    result.add_error(f"{slot_prefix}min_length cannot be greater than max_length")

            if slot_type in ('select', 'multiselect', 'radio'):
                options = slot.get('options')
                if not options or not isinstance(options, list):
                    result.add_error(f"{slot_prefix}'{slot_type}' type requires 'options' array")

            if slot_type == 'reference':
                if not slot.get('reference_type'):
                    result.add_error(f"{slot_prefix}'reference' type requires 'reference_type' field")

        return result

    def validate_defaults(self, defaults: dict, block_def, prefix: str = "") -> ValidationResult:
        """Validate default values against their schemas."""
        result = ValidationResult()

        if not isinstance(defaults, dict):
            result.add_error(f"{prefix}defaults must be an object")
            return result

        if 'variant' in defaults:
            variant_id = defaults['variant']
            if block_def.variants and not any(v.get('id') == variant_id for v in block_def.variants):
                result.add_error(f"{prefix}defaults.variant '{variant_id}' not found in variants")

        if 'toggles' in defaults:
            toggle_defaults = defaults['toggles']
            if not isinstance(toggle_defaults, dict):
                result.add_error(f"{prefix}defaults.toggles must be an object")
            else:
                toggle_ids = {t.get('id') for t in block_def.feature_toggles}
                for toggle_key in toggle_defaults:
                    if toggle_key not in toggle_ids:
                        result.add_warning(f"{prefix}defaults.toggles.{toggle_key} not found in feature_toggles")

        if 'styles' in defaults:
            style_defaults = defaults['styles']
            if not isinstance(style_defaults, dict):
                result.add_error(f"{prefix}defaults.styles must be an object")
            else:
                for axis, value in style_defaults.items():
                    if axis not in block_def.style_axes:
                        result.add_warning(f"{prefix}defaults.styles.{axis} not found in style_axes")
                    elif value not in block_def.style_axes.get(axis, []):
                        result.add_error(f"{prefix}defaults.styles.{axis} value '{value}' is not a valid option")

        result.merge(self.check_security(defaults, f"{prefix}defaults"))

        return result

    def check_security(self, content: Any, context: str = "") -> ValidationResult:
        """
        Check content for potentially dangerous executable code.
        """
        result = ValidationResult()

        if isinstance(content, str):
            self._check_string_security(content, context, result)
        elif isinstance(content, dict):
            for key, value in content.items():
                sub_context = f"{context}.{key}" if context else key
                result.merge(self.check_security(value, sub_context))
        elif isinstance(content, list):
            for i, item in enumerate(content):
                sub_context = f"{context}[{i}]" if context else f"[{i}]"
                result.merge(self.check_security(item, sub_context))

        return result

    def _check_string_security(self, text: str, context: str, result: ValidationResult) -> None:
        """Check a string for dangerous patterns."""
        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(text):
                result.add_error(f"Potentially dangerous code detected in {context}: matches pattern '{pattern.pattern}'")

    def validate_manifest(self, manifest: dict) -> ValidationResult:
        """Validate a bundle manifest structure."""
        result = ValidationResult()

        if not isinstance(manifest, dict):
            result.add_error("Manifest must be a JSON object")
            return result

        if 'blocks' in manifest:
            blocks = manifest['blocks']
            if not isinstance(blocks, list):
                result.add_error("manifest.blocks must be an array")
            else:
                for i, block in enumerate(blocks):
                    block_result = self.validate_manifest_block(block, f"manifest.blocks[{i}]")
                    result.merge(block_result)

        result.merge(self.check_security(manifest, "manifest"))

        return result

    def validate_manifest_block(self, block: dict, prefix: str) -> ValidationResult:
        """Validate a single block definition within a manifest."""
        result = ValidationResult()

        if not isinstance(block, dict):
            result.add_error(f"{prefix}: must be an object")
            return result

        if not block.get('block_type_id'):
            result.add_error(f"{prefix}: block_type_id is required")

        if not block.get('name'):
            result.add_error(f"{prefix}: name is required")

        if 'variants' in block:
            result.merge(self.validate_variants(block['variants'], f"{prefix}."))

        if 'feature_toggles' in block:
            result.merge(self.validate_toggles(block['feature_toggles'], f"{prefix}."))

        if 'style_axes' in block:
            result.merge(self.validate_style_axes(block['style_axes'], f"{prefix}."))

        if 'content_slots' in block:
            result.merge(self.validate_content_slots(block['content_slots'], f"{prefix}."))

        return result


bundle_validation_service = BundleValidationService()
