import re
import uuid
from typing import Any, Iterable, Mapping, MutableMapping

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import JSONField
from django.utils import timezone

from crm.models import Contact
from portal.models import Tenant, TenantScopedModel


class VisitorSession(models.Model):
    """Track visitor sessions tied to the marketing landing experience."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(
        Contact,
        related_name="visitor_sessions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    referral_source = models.CharField(max_length=255, blank=True)
    utm_source = models.CharField(max_length=255, blank=True)
    utm_medium = models.CharField(max_length=255, blank=True)
    utm_campaign = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    total_messages = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_engaged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", )

    def touch(self):
        self.last_engaged_at = timezone.now()
        self.save(update_fields=["last_engaged_at", "updated_at"])


class Topic(models.Model):
    """Content holder for blocks - provides the actual data to fill block templates"""

    slug = models.SlugField(primary_key=True)
    title = models.CharField(max_length=255)
    short_description = models.TextField(blank=True)
    icon = models.CharField(max_length=255, blank=True)
    color = models.CharField(max_length=32, blank=True)
    image = models.URLField(blank=True)
    marketing_copy = models.TextField(blank=True)
    benefits = models.JSONField(default=list, blank=True)
    use_cases = models.JSONField(default=list, blank=True)
    pricing_tiers = models.JSONField(default=list, blank=True)
    features = models.JSONField(default=list, blank=True)
    cta = models.JSONField(default=dict, blank=True)
    markdown = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title", )

    def __str__(self) -> str:
        return self.title


class TopicVisit(models.Model):
    session = models.ForeignKey(VisitorSession,
                                related_name="topic_visits",
                                on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic,
                              related_name="visits",
                              on_delete=models.CASCADE)
    visited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-visited_at", )


class ConversationTurn(models.Model):
    session = models.ForeignKey(VisitorSession,
                                related_name="conversation_turns",
                                on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic,
                              related_name="conversation_turns",
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True)
    user_message = models.TextField()
    assistant_message = models.TextField()
    suggestions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", )


class Like(models.Model):
    session = models.ForeignKey(VisitorSession,
                                related_name="likes",
                                on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic,
                              related_name="likes",
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True)
    message_index = models.PositiveIntegerField()
    message = models.ForeignKey(
        "ConversationMessage",
        related_name="likes",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", )
        unique_together = ("session", "message_index")

    def clean(self):
        if self.message and self.message.session_id != self.session_id:
            raise ValidationError({
                "message":
                "Like must reference a message from the same session."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class EmailLog(models.Model):
    session = models.ForeignKey(VisitorSession,
                                related_name="email_logs",
                                on_delete=models.SET_NULL,
                                null=True,
                                blank=True)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    summary_included = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-sent_at", )


class WhatsAppLog(models.Model):
    session = models.ForeignKey(VisitorSession,
                                related_name="whatsapp_logs",
                                on_delete=models.SET_NULL,
                                null=True,
                                blank=True)
    recipient = models.CharField(max_length=255)
    status = models.CharField(max_length=64)
    template_name = models.CharField(max_length=255, blank=True)
    deep_link = models.URLField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-sent_at", )


class MeetingBooking(models.Model):
    PROVIDER_CHOICES = (
        ("calendly", "Calendly"),
        ("google", "Google Calendar"),
        ("custom", "Custom"),
    )

    session = models.ForeignKey(VisitorSession,
                                related_name="meetings",
                                on_delete=models.SET_NULL,
                                null=True,
                                blank=True)
    attendee_name = models.CharField(max_length=255)
    attendee_email = models.EmailField()
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    scheduled_for = models.DateTimeField()
    confirmation_message = models.CharField(max_length=255)
    calendar_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", )


# ---------------------------------------------------------------------------
# Content models
# ---------------------------------------------------------------------------

LOCALE_PATTERN = re.compile(r"^[a-z]{2}(?:[-_][A-Za-z]{2})?$")

BLOCK_TYPE_HERO = "hero"
BLOCK_TYPE_RICH_TEXT = "rich_text"
BLOCK_TYPE_FEATURE_LIST = "feature_list"
BLOCK_TYPE_CTA = "cta"

# ---------------------------------------------------------------------------
# CTA Action Types - reusable across all blocks with buttons/links
# ---------------------------------------------------------------------------
ACTION_TYPE_NONE = "none"
ACTION_TYPE_EXTERNAL_LINK = "external_link"
ACTION_TYPE_INTERNAL_LINK = "internal_link"
ACTION_TYPE_SCROLL_TO_ANCHOR = "scroll_to_anchor"
ACTION_TYPE_TOPIC_CHAT = "topic_chat"
ACTION_TYPE_ARTICLE_CHAT = "article_chat"
ACTION_TYPE_SIMPLE_MODAL = "simple_modal"
ACTION_TYPE_LEGAL_DOCUMENT = "legal_document"
ACTION_TYPE_REVEAL_CONTENT = "reveal_content"
ACTION_TYPE_COLLAPSE_CONTENT = "collapse_content"

VALID_ACTION_TYPES = {
    ACTION_TYPE_NONE,
    ACTION_TYPE_EXTERNAL_LINK,
    ACTION_TYPE_INTERNAL_LINK,
    ACTION_TYPE_SCROLL_TO_ANCHOR,
    ACTION_TYPE_TOPIC_CHAT,
    ACTION_TYPE_ARTICLE_CHAT,
    ACTION_TYPE_SIMPLE_MODAL,
    ACTION_TYPE_LEGAL_DOCUMENT,
    ACTION_TYPE_REVEAL_CONTENT,
    ACTION_TYPE_COLLAPSE_CONTENT,
}


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("_", "-").lower()


def _validate_locale(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not LOCALE_PATTERN.match(value):
        raise ValidationError(
            {field: "Locale values must be strings like 'en' or 'en-US'."})
    return normalize_locale(value)


def _require_keys(payload: Mapping[str, Any], required: Iterable[str], *,
                  block_type: str) -> None:
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValidationError({
            "payload":
            f"Block type '{block_type}' requires fields: {', '.join(missing)}.",
        })


def _ensure_type(value: Any, expected_type: type | tuple[type, ...],
                 field_path: str, *, block_type: str) -> None:
    if not isinstance(value, expected_type):
        expected_name = (expected_type.__name__ if isinstance(
            expected_type, type) else " or ".join(t.__name__
                                                  for t in expected_type))
        raise ValidationError({
            "payload":
            f"Field '{field_path}' for block type '{block_type}' must be {expected_name}.",
        })


def _ensure_non_empty_string(value: Any, field_path: str, *,
                             block_type: str) -> None:
    _ensure_type(value, str, field_path, block_type=block_type)
    if not value.strip():
        raise ValidationError({
            "payload":
            f"Field '{field_path}' for block type '{block_type}' cannot be blank.",
        })


def validate_action(action: Any, field_path: str, *, block_type: str) -> Mapping[str, Any]:
    """Validate CTA action object with type-specific field requirements.
    
    Supports 10 action types:
    - none: No action (disabled CTA)
    - external_link: Opens URL in new tab (requires href)
    - internal_link: Router navigation (requires page_slug)
    - scroll_to_anchor: Smooth scroll (requires anchor_id)
    - topic_chat: Opens chat modal for a service/topic (requires topic_slug)
    - article_chat: Opens chat modal for a blog article (requires article_slug)
    - simple_modal: Opens a modal with content (requires modal_content_key)
    - legal_document: Opens legal doc modal (requires legal_doc_slug)
    - reveal_content: Toggles visibility of target block (requires target_block_key)
    - collapse_content: Toggles collapse state (requires target_block_key)
    """
    if not isinstance(action, Mapping):
        raise ValidationError({
            "payload":
            f"Field '{field_path}' for block type '{block_type}' must be an action object."
        })
    
    action_type = action.get("type")
    if not action_type:
        raise ValidationError({
            "payload":
            f"Field '{field_path}.type' is required for block type '{block_type}'."
        })
    
    if action_type not in VALID_ACTION_TYPES:
        raise ValidationError({
            "payload":
            f"Invalid action type '{action_type}' in '{field_path}'. "
            f"Valid types: {', '.join(sorted(VALID_ACTION_TYPES))}."
        })
    
    # Type-specific validation
    if action_type == ACTION_TYPE_NONE:
        pass  # No additional fields required
    
    elif action_type == ACTION_TYPE_EXTERNAL_LINK:
        if "href" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'href' in '{field_path}'."
            })
        _ensure_non_empty_string(action["href"], f"{field_path}.href", block_type=block_type)
    
    elif action_type == ACTION_TYPE_INTERNAL_LINK:
        if "page_slug" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'page_slug' in '{field_path}'."
            })
        _ensure_non_empty_string(action["page_slug"], f"{field_path}.page_slug", block_type=block_type)
    
    elif action_type == ACTION_TYPE_SCROLL_TO_ANCHOR:
        if "anchor_id" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'anchor_id' in '{field_path}'."
            })
        _ensure_non_empty_string(action["anchor_id"], f"{field_path}.anchor_id", block_type=block_type)
    
    elif action_type == ACTION_TYPE_TOPIC_CHAT:
        if "topic_slug" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'topic_slug' in '{field_path}'."
            })
        _ensure_non_empty_string(action["topic_slug"], f"{field_path}.topic_slug", block_type=block_type)
        # Optional: agent_id for specific agent override
        if "agent_id" in action:
            _ensure_non_empty_string(action["agent_id"], f"{field_path}.agent_id", block_type=block_type)
    
    elif action_type == ACTION_TYPE_ARTICLE_CHAT:
        if "article_slug" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'article_slug' in '{field_path}'."
            })
        _ensure_non_empty_string(action["article_slug"], f"{field_path}.article_slug", block_type=block_type)
        # Optional: agent_id for specific agent override
        if "agent_id" in action:
            _ensure_non_empty_string(action["agent_id"], f"{field_path}.agent_id", block_type=block_type)
    
    elif action_type == ACTION_TYPE_SIMPLE_MODAL:
        if "modal_content_key" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'modal_content_key' in '{field_path}'."
            })
        _ensure_non_empty_string(action["modal_content_key"], f"{field_path}.modal_content_key", block_type=block_type)
    
    elif action_type == ACTION_TYPE_LEGAL_DOCUMENT:
        if "legal_doc_slug" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'legal_doc_slug' in '{field_path}'."
            })
        _ensure_non_empty_string(action["legal_doc_slug"], f"{field_path}.legal_doc_slug", block_type=block_type)
    
    elif action_type in (ACTION_TYPE_REVEAL_CONTENT, ACTION_TYPE_COLLAPSE_CONTENT):
        if "target_block_key" not in action:
            raise ValidationError({
                "payload":
                f"Action type '{action_type}' requires 'target_block_key' in '{field_path}'."
            })
        _ensure_non_empty_string(action["target_block_key"], f"{field_path}.target_block_key", block_type=block_type)
    
    return action


def validate_hidden_content(hidden: Any, *, block_type: str) -> Mapping[str, Any]:
    """Validate hidden content for conversation initiators and agent instructions.
    
    Hidden content is not rendered but passed to chat context when actions trigger conversations.
    Supports:
    - conversation_initiator: Initial context/prompt for the conversation
    - agent_instructions: Specific instructions for the agent handling the chat
    """
    if hidden is None:
        return {}
    
    if not isinstance(hidden, Mapping):
        raise ValidationError({
            "hidden":
            f"Hidden content for block type '{block_type}' must be a JSON object."
        })
    
    conversation_initiator = hidden.get("conversation_initiator")
    if conversation_initiator is not None:
        if not isinstance(conversation_initiator, str):
            raise ValidationError({
                "hidden":
                f"Field 'conversation_initiator' for block type '{block_type}' must be a string."
            })
    
    agent_instructions = hidden.get("agent_instructions")
    if agent_instructions is not None:
        if not isinstance(agent_instructions, str):
            raise ValidationError({
                "hidden":
                f"Field 'agent_instructions' for block type '{block_type}' must be a string."
            })
    
    return hidden


def validate_cta_object(cta: Any, field_path: str, *, block_type: str, 
                        require_action: bool = True) -> Mapping[str, Any]:
    """Validate a CTA object with label and action.
    
    Supports both legacy format (label + href) and new format (label + action).
    """
    _ensure_type(cta, Mapping, field_path, block_type=block_type)
    
    if "label" not in cta:
        raise ValidationError({
            "payload":
            f"Field '{field_path}.label' is required for block type '{block_type}'."
        })
    _ensure_non_empty_string(cta["label"], f"{field_path}.label", block_type=block_type)
    
    # Support both legacy href and new action format
    has_href = "href" in cta
    has_action = "action" in cta
    
    if has_action:
        validate_action(cta["action"], f"{field_path}.action", block_type=block_type)
    elif has_href:
        # Legacy format - validate href as external_link action
        _ensure_non_empty_string(cta["href"], f"{field_path}.href", block_type=block_type)
    elif require_action:
        raise ValidationError({
            "payload":
            f"Field '{field_path}' requires either 'action' or 'href' for block type '{block_type}'."
        })
    
    return cta


def validate_block_payload(block_type: str,
                           payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate payloads for discriminated content blocks."""

    if not isinstance(payload, Mapping):
        raise ValidationError({"payload": "Payload must be a JSON object."})

    if block_type == BLOCK_TYPE_HERO:
        _require_keys(payload, ("headline", "cta"), block_type=block_type)
        _ensure_non_empty_string(payload["headline"],
                                 "headline",
                                 block_type=block_type)
        # Validate CTA with action support (accepts both legacy href and new action format)
        validate_cta_object(payload["cta"], "cta", block_type=block_type)
        subheadline = payload.get("subheadline")
        if subheadline is not None:
            _ensure_type(subheadline,
                         str,
                         "subheadline",
                         block_type=block_type)
        image = payload.get("image")
        if image is not None:
            _ensure_non_empty_string(image, "image", block_type=block_type)
        # Validate optional hidden content for conversation context
        if "hidden" in payload:
            validate_hidden_content(payload["hidden"], block_type=block_type)
        return payload

    if block_type == BLOCK_TYPE_RICH_TEXT:
        _require_keys(payload, ("markdown", ), block_type=block_type)
        _ensure_non_empty_string(payload["markdown"],
                                 "markdown",
                                 block_type=block_type)
        return payload

    if block_type == BLOCK_TYPE_FEATURE_LIST:
        _require_keys(payload, ("features", ), block_type=block_type)
        features = payload["features"]
        _ensure_type(features, (list, tuple),
                     "features",
                     block_type=block_type)
        if not features:
            raise ValidationError({
                "payload":
                "Feature list blocks require at least one feature."
            })
        for index, feature in enumerate(features):
            field_path = f"features[{index}]"
            _ensure_type(feature, Mapping, field_path, block_type=block_type)
            _require_keys(feature, ("title", "description"),
                          block_type=block_type)
            _ensure_non_empty_string(feature["title"],
                                     f"{field_path}.title",
                                     block_type=block_type)
            _ensure_non_empty_string(feature["description"],
                                     f"{field_path}.description",
                                     block_type=block_type)
            icon = feature.get("icon")
            if icon is not None:
                _ensure_type(icon,
                             str,
                             f"{field_path}.icon",
                             block_type=block_type)
        return payload

    if block_type == BLOCK_TYPE_CTA:
        _require_keys(payload, ("title", "primaryCta"), block_type=block_type)
        _ensure_non_empty_string(payload["title"],
                                 "title",
                                 block_type=block_type)
        # Validate primary CTA with action support
        validate_cta_object(payload["primaryCta"], "primaryCta", block_type=block_type)
        # Validate optional secondary CTA (action not required)
        secondary = payload.get("secondaryCta")
        if secondary is not None:
            validate_cta_object(secondary, "secondaryCta", block_type=block_type, require_action=False)
        body = payload.get("body")
        if body is not None:
            _ensure_type(body, str, "body", block_type=block_type)
        # Validate optional hidden content for conversation context
        if "hidden" in payload:
            validate_hidden_content(payload["hidden"], block_type=block_type)
        return payload

    raise ValidationError({"type": f"Unsupported block type '{block_type}'."})


"""
class ContentPage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=200)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    layout = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    default_locale = models.CharField(max_length=10, default="en")
    metadata = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("slug",)

    def clean(self):
        self.default_locale = _validate_locale(self.default_locale, "default_locale") or "en"

    def __str__(self) -> str:
        return self.slug

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
"""
"""
class ContentBlock(models.Model):

    class BlockType(models.TextChoices):
        HERO = BLOCK_TYPE_HERO, "Hero"
        RICH_TEXT = BLOCK_TYPE_RICH_TEXT, "Rich Text"
        FEATURE_LIST = BLOCK_TYPE_FEATURE_LIST, "Feature List"
        CTA = BLOCK_TYPE_CTA, "Call To Action"
        SERVICES = "services", "Services"
        TOPIC_CONTENT = "topic_content", "Topic Content"

    page = models.ForeignKey(ContentPage, related_name="blocks", null=True, on_delete=models.CASCADE)
    key = models.CharField(max_length=150)
    type = models.CharField(max_length=40, choices=BlockType.choices)
    topic = models.ForeignKey(Topic, related_name="blocks", on_delete=models.SET_NULL, null=True, blank=True)
    layout = models.CharField(max_length=100, blank=True)
    config = JSONField(default=dict, blank=True)
    locale = models.CharField(max_length=10, default="en")
    fallback_locale = models.CharField(max_length=10, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    metadata = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")

    def clean(self):
        normalized_locale = _validate_locale(self.locale, "locale")
        self.locale = normalized_locale or "en"
        normalized_fallback = _validate_locale(self.fallback_locale, "fallback_locale")
        self.fallback_locale = normalized_fallback or ""


    @property
    def is_orphaned(self):

        # For block types that should have topics
        if self.type in [self.BlockType.TOPIC_CONTENT, self.BlockType.SERVICES]:
            return self.topic is None
        return False

    def save(self, *args, **kwargs):
        # Track topic changes
        if self.pk:
            try:
                old_instance = ContentBlock.objects.get(pk=self.pk)
                if old_instance.topic != self.topic:
                    # Topic changed - you can log this, emit a signal, etc.
                    old_topic_slug = old_instance.topic.slug if old_instance.topic else None
                    new_topic_slug = self.topic.slug if self.topic else None
                    self.metadata = self.metadata or {}
                    self.metadata['topic_history'] = self.metadata.get('topic_history', [])
                    self.metadata['topic_history'].append({
                        'changed_at': timezone.now().isoformat(),
                        'from': old_topic_slug,
                        'to': new_topic_slug,
                    })
                    # Keep only last 10 changes
                    self.metadata['topic_history'] = self.metadata['topic_history'][-10:]
            except ContentBlock.DoesNotExist:
                pass

        self.full_clean()
        return super().save(*args, **kwargs)

    def get_content(self):
        
        if self.topic:
            return {
                "type": self.type,
                "layout": self.layout,
                "config": self.config,
                "content": {
                    "title": self.topic.title,
                    "description": self.topic.short_description,
                    "image": self.topic.image,
                    "marketing_copy": self.topic.marketing_copy,
                    "benefits": self.topic.benefits,
                    "use_cases": self.topic.use_cases,
                    "features": self.topic.features,
                    "pricing_tiers": self.topic.pricing_tiers,
                    "cta": self.topic.cta,
                },
            }
        return {
            "type": self.type,
            "layout": self.layout,
            "config": self.config,
        }
"""


class Conversation(models.Model):
    session = models.ForeignKey(VisitorSession,
                                related_name="conversations",
                                on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic,
                              related_name="conversations",
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True)
    conversation_date = models.DateField(default=timezone.localdate)
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)
    metadata = JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-last_message_at", "-id")
        unique_together = (("session", "topic", "conversation_date"), )

    def touch(self):
        self.last_message_at = timezone.now()
        self.save(update_fields=["last_message_at"])  # pragma: no cover


class ConversationMessage(models.Model):

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(Conversation,
                                     related_name="messages",
                                     on_delete=models.CASCADE)
    session = models.ForeignKey(VisitorSession,
                                related_name="conversation_messages",
                                on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic,
                              related_name="conversation_messages",
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    suggestions = JSONField(default=list, blank=True)
    metadata = JSONField(default=dict, blank=True)
    conversation_sequence = models.PositiveIntegerField()
    session_sequence = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("conversation_sequence", "id")
        unique_together = (
            ("conversation", "conversation_sequence"),
            ("session", "session_sequence"),
        )
        indexes = (
            models.Index(fields=("session", "created_at")),
            models.Index(fields=("conversation", "created_at")),
            models.Index(fields=("session", "topic", "created_at")),
        )

    def clean(self):
        if self.role == self.Role.ASSISTANT and not isinstance(
                self.suggestions, list):
            raise ValidationError(
                {"suggestions": "Assistant suggestions must be a list."})
        if self.role == self.Role.USER and self.suggestions:
            raise ValidationError(
                {"suggestions": "User messages cannot include suggestions."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class FluidPage(TenantScopedModel):
    """Main page model for FluidCMS - tenant-scoped with UUID primary key"""

    class PageStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        LIVE = 'live', 'Live'
        PUBLIC = 'public', 'Public'
        ARCHIVE = 'archive', 'Archive'
        PRIVATE = 'private', 'Private'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant,
                               on_delete=models.CASCADE,
                               related_name='fluid_pages')
    slug = models.SlugField(max_length=200)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    layout = models.CharField(max_length=150, blank=True, default='')
    status = models.CharField(max_length=20,
                              choices=PageStatus.choices,
                              default=PageStatus.DRAFT)
    is_active = models.BooleanField(default=True)
    is_home = models.BooleanField(default=False)
    default_locale = models.CharField(max_length=10, default='en')
    metadata = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('slug', )
        unique_together = (('tenant', 'slug'), )
        indexes = [
            models.Index(fields=['tenant', 'slug']),
            models.Index(fields=['tenant', 'is_home']),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.nombre} - {self.slug}"

    def clean(self):
        # Ensure only one home page per tenant
        if self.is_home:
            existing_home = FluidPage.objects.filter(
                tenant=self.tenant, is_home=True).exclude(id=self.id).first()

            if existing_home:
                raise ValidationError({
                    'is_home':
                    f'Tenant {self.tenant.nombre} already has a home page: {existing_home.slug}'
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FluidBlock(TenantScopedModel):
    """Content block model for FluidCMS - defines structure and content"""

    class BlockType(models.TextChoices):
        HEADER = 'header', 'Header'
        HERO = 'hero', 'Hero'
        RICH_TEXT = 'rich_text', 'Rich Text'
        FEATURE_LIST = 'feature_list', 'Feature List'
        HEADING_CONTENT = 'heading_content', 'Heading Content'
        FEATURED = 'featured', 'Featured'
        CTA = 'cta', 'Call To Action'
        BLOG = 'blog', 'Blog'
        NEWS = 'news', 'News'
        SERVICES = 'services', 'Services'
        TOPIC_CONTENT = 'topic_content', 'Topic Content'
        KPI = 'kpi', 'KPI'
        ARTICLES = 'articles', 'Articles'
        FAQ = 'faq', 'FAQ'
        TESTIMONIALS = 'testimonials', 'Testimonials'
        BRANDS = 'brands', 'Brands/Logos'
        CONTACT_INFO = 'contact_info', 'Contact Info'
        QUOTE = 'quote', 'Quote'
        FOOTER = 'footer', 'Footer'
        CUSTOM = 'custom', 'Custom'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant,
                               on_delete=models.CASCADE,
                               related_name='fluid_blocks')
    page = models.ForeignKey(FluidPage,
                             related_name='blocks',
                             on_delete=models.CASCADE)
    key = models.CharField(max_length=150)
    type = models.CharField(max_length=40, choices=BlockType.choices)
    layout = JSONField(default=dict, blank=True)
    config = JSONField(default=dict, blank=True)
    locale = models.CharField(max_length=10, default='en')
    fallback_locale = models.CharField(max_length=10, blank=True, default='')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    metadata = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('order', 'created_at')
        indexes = [
            models.Index(fields=['page', 'order']),
            models.Index(fields=['page', 'key', 'locale']),
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self) -> str:
        return f"{self.page.slug} - {self.key} ({self.type})"

    def clean(self):
        # Ensure tenant consistency
        if self.page and self.page.tenant != self.tenant:
            raise ValidationError(
                {'page': 'Block must belong to the same tenant as its page'})

    def save(self, *args, **kwargs):
        # Auto-set tenant from page if not set
        if self.page and not self.tenant_id:
            self.tenant = self.page.tenant
        self.full_clean()
        super().save(*args, **kwargs)


def fluidmedia_upload_path(instance, filename):
    """Generate upload path: fluidcms/{tenant_id}/{uuid}_{filename}"""
    return f"fluidcms/{instance.tenant_id}/{instance.id}_{filename}"


class FluidMedia(TenantScopedModel):
    """Media assets for FluidCMS - tenant-scoped with S3 storage"""

    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'
        DOCUMENT = 'document', 'Document'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant,
                               on_delete=models.CASCADE,
                               related_name='fluid_media')
    file = models.FileField(upload_to=fluidmedia_upload_path)
    filename = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.OTHER)
    mime_type = models.CharField(max_length=100, blank=True, default='')
    size = models.PositiveIntegerField(default=0)
    metadata = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['tenant', 'type']),
            models.Index(fields=['tenant', 'created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.filename} ({self.type})"

    @property
    def url(self):
        """Returns presigned URL for the file"""
        if self.file:
            return self.file.url
        return None


# ---------------------------------------------------------------------------
# Articles Repository Models
# ---------------------------------------------------------------------------


class ArticleCategory(TenantScopedModel):
    """Categories for organizing articles with optional hierarchy"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='article_categories'
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True, default='')
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children'
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'landing_api'
        ordering = ('order', 'name')
        unique_together = (('tenant', 'slug'),)
        verbose_name = 'Article Category'
        verbose_name_plural = 'Article Categories'
        indexes = [
            models.Index(fields=['tenant', 'slug']),
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self) -> str:
        return self.name


class ArticleTag(TenantScopedModel):
    """Tags for labeling and filtering articles"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='article_tags'
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    color = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'landing_api'
        ordering = ('name',)
        unique_together = (('tenant', 'slug'),)
        verbose_name = 'Article Tag'
        verbose_name_plural = 'Article Tags'
        indexes = [
            models.Index(fields=['tenant', 'slug']),
        ]

    def __str__(self) -> str:
        return self.name


class Article(TenantScopedModel):
    """Blog articles/posts with rich content and metadata"""

    class ArticleStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='articles'
    )
    author = models.ForeignKey(
        'portal.MoioUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles'
    )
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300)
    excerpt = models.TextField(blank=True, default='')
    content = models.TextField(blank=True, default='')
    category = models.ForeignKey(
        ArticleCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles'
    )
    tags = models.ManyToManyField(
        ArticleTag,
        blank=True,
        related_name='articles'
    )
    featured_image = models.ForeignKey(
        FluidMedia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='featured_articles'
    )
    status = models.CharField(
        max_length=20,
        choices=ArticleStatus.choices,
        default=ArticleStatus.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    metadata = JSONField(default=dict, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    reading_time_minutes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'landing_api'
        ordering = ('-published_at', '-created_at')
        unique_together = (('tenant', 'slug'),)
        verbose_name = 'Article'
        verbose_name_plural = 'Articles'
        indexes = [
            models.Index(fields=['tenant', 'slug']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'published_at']),
            models.Index(fields=['tenant', 'category']),
        ]

    def __str__(self) -> str:
        return self.title

    def publish(self):
        """Publish the article. Can be called on draft or archived articles."""
        if self.status == self.ArticleStatus.PUBLISHED:
            return  # Already published, no-op
        self.status = self.ArticleStatus.PUBLISHED
        if not self.published_at:
            self.published_at = timezone.now()
        self.save(update_fields=['status', 'published_at', 'updated_at'])

    def archive(self):
        """Archive the article. Can be called on any non-archived article."""
        if self.status == self.ArticleStatus.ARCHIVED:
            return  # Already archived, no-op
        self.status = self.ArticleStatus.ARCHIVED
        self.save(update_fields=['status', 'updated_at'])

    def calculate_reading_time(self) -> int:
        """Calculate reading time based on content length (average 200 words per minute)"""
        if not self.content:
            return 0
        word_count = len(self.content.split())
        return max(1, round(word_count / 200))


# ---------------------------------------------------------------------------
# Block Bundle System Models
# ---------------------------------------------------------------------------


class BlockBundle(models.Model):
    """
    A collection of block definitions created by designers.
    Bundles can be global (platform-wide) or tenant-specific.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True, default='')
    author = models.CharField(max_length=200, blank=True, default='')
    is_global = models.BooleanField(
        default=False,
        help_text='If True, bundle is available platform-wide. If False, bundle is tenant-specific.'
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='block_bundles',
        null=True,
        blank=True,
        help_text='Owner tenant for non-global bundles. Null for global bundles.'
    )
    metadata = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_global']),
            models.Index(fields=['tenant']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    def clean(self):
        if not self.is_global and not self.tenant:
            raise ValidationError({
                'tenant': 'Non-global bundles must have an owner tenant.'
            })
        if self.is_global and self.tenant:
            raise ValidationError({
                'tenant': 'Global bundles cannot have an owner tenant.'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BlockBundleVersion(models.Model):
    """
    A specific version of a block bundle with lifecycle states.
    Contains all block definitions for that version.
    Immutable once published.
    """

    class VersionStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted for Review'
        PUBLISHED = 'published', 'Published'
        DEPRECATED = 'deprecated', 'Deprecated'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bundle = models.ForeignKey(
        BlockBundle,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version = models.CharField(
        max_length=50,
        help_text='Semantic version string (e.g., 1.0.0, 1.2.3-beta)'
    )
    changelog = models.TextField(
        blank=True,
        default='',
        help_text='Description of changes in this version'
    )
    status = models.CharField(
        max_length=20,
        choices=VersionStatus.choices,
        default=VersionStatus.DRAFT
    )
    manifest = JSONField(
        default=dict,
        blank=True,
        help_text='Full bundle manifest including block definitions, metadata, and configuration'
    )
    compatibility_range = JSONField(
        default=dict,
        blank=True,
        help_text='Platform version requirements (e.g., {"min_version": "1.0.0", "max_version": "2.0.0"})'
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        'portal.MoioUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='published_bundle_versions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        unique_together = (('bundle', 'version'),)
        indexes = [
            models.Index(fields=['bundle', 'status']),
            models.Index(fields=['bundle', 'version']),
            models.Index(fields=['status']),
        ]

    def __str__(self) -> str:
        return f"{self.bundle.name} v{self.version} ({self.status})"

    def clean(self):
        if self.status == self.VersionStatus.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_immutable(self) -> bool:
        """Published or deprecated versions cannot be modified."""
        return self.status in (self.VersionStatus.PUBLISHED, self.VersionStatus.DEPRECATED)

    # ---------------------------------------------------------------------------
    # Lifecycle State Machine Methods
    # ---------------------------------------------------------------------------

    VALID_TRANSITIONS = {
        VersionStatus.DRAFT: [VersionStatus.SUBMITTED],
        VersionStatus.SUBMITTED: [VersionStatus.DRAFT, VersionStatus.PUBLISHED],
        VersionStatus.PUBLISHED: [VersionStatus.DEPRECATED],
        VersionStatus.DEPRECATED: [],
    }

    def can_transition_to(self, target_status: str) -> bool:
        """Check if transition to target status is valid."""
        valid_targets = self.VALID_TRANSITIONS.get(self.status, [])
        return target_status in valid_targets

    def _do_transition(self, target_status: str, user=None) -> None:
        """Internal method to perform a state transition."""
        if not self.can_transition_to(target_status):
            raise ValidationError({
                'status': f"Cannot transition from '{self.status}' to '{target_status}'"
            })
        self.status = target_status
        if target_status == self.VersionStatus.PUBLISHED:
            self.published_at = timezone.now()
            self.published_by = user
        self.save()

    def submit(self) -> None:
        """
        Submit bundle version for review. Transition: Draft → Submitted.
        Also materializes BlockDefinition instances from the manifest.
        """
        self._do_transition(self.VersionStatus.SUBMITTED)
        self.materialize_block_definitions()

    def reject(self) -> None:
        """Reject submitted bundle version. Transition: Submitted → Draft."""
        self._do_transition(self.VersionStatus.DRAFT)

    def publish(self, user=None, skip_validation: bool = False) -> None:
        """
        Publish bundle version. Transition: Submitted → Published.
        Requires prior validation to pass unless skip_validation=True.
        Also re-materializes BlockDefinition instances to ensure consistency.
        """
        if not skip_validation:
            from .services import bundle_validation_service
            result = bundle_validation_service.validate_bundle_version(self)
            if not result.is_valid:
                raise ValidationError({
                    'validation': 'Bundle version has validation errors and cannot be published',
                    'errors': result.errors,
                })
        self._do_transition(self.VersionStatus.PUBLISHED, user=user)
        self.materialize_block_definitions()

    def deprecate(self) -> None:
        """Deprecate published bundle version. Transition: Published → Deprecated."""
        self._do_transition(self.VersionStatus.DEPRECATED)

    def get_available_transitions(self) -> list[str]:
        """Get list of valid target statuses from current state."""
        return list(self.VALID_TRANSITIONS.get(self.status, []))

    @classmethod
    def create_new_version(cls, bundle: 'BlockBundle', version: str, user=None):
        """
        Create a new draft version for a bundle.
        Optionally clone from the latest published version.
        """
        latest_published = cls.objects.filter(
            bundle=bundle,
            status=cls.VersionStatus.PUBLISHED
        ).order_by('-published_at').first()

        manifest = {}
        if latest_published:
            manifest = latest_published.manifest.copy() if latest_published.manifest else {}

        new_version = cls(
            bundle=bundle,
            version=version,
            status=cls.VersionStatus.DRAFT,
            manifest=manifest,
        )
        new_version.save()
        return new_version

    def materialize_block_definitions(self) -> list['BlockDefinition']:
        """
        Create BlockDefinition instances from the manifest.
        Should be called when transitioning to SUBMITTED or PUBLISHED.
        Returns list of created BlockDefinition instances.
        """
        if not self.manifest or 'blocks' not in self.manifest:
            return []

        blocks_data = self.manifest.get('blocks', [])
        created_definitions = []

        self.block_definitions.all().delete()

        for block_data in blocks_data:
            if not isinstance(block_data, dict):
                continue

            block_type_id = block_data.get('block_type_id')
            if not block_type_id:
                continue

            block_def = BlockDefinition(
                bundle_version=self,
                block_type_id=block_type_id,
                name=block_data.get('name', block_type_id),
                description=block_data.get('description', ''),
                icon=block_data.get('icon', ''),
                category=block_data.get('category', ''),
                variants=block_data.get('variants', []),
                feature_toggles=block_data.get('feature_toggles', []),
                style_axes=block_data.get('style_axes', {}),
                content_slots=block_data.get('content_slots', []),
                defaults=block_data.get('defaults', {}),
                preview_template=block_data.get('preview_template', ''),
                metadata=block_data.get('metadata', {}),
            )
            block_def.save()
            created_definitions.append(block_def)

        return created_definitions

    def update_manifest(self, new_manifest: dict) -> None:
        """
        Update the manifest. Only allowed for DRAFT versions.
        """
        if self.status != self.VersionStatus.DRAFT:
            raise ValidationError({
                'manifest': f'Cannot modify manifest of a {self.status} version. Only draft versions can be edited.'
            })
        self.manifest = new_manifest
        self.save(update_fields=['manifest', 'updated_at'])


class BlockDefinition(models.Model):
    """
    A typed block template within a bundle version.
    Defines variants, toggles, style axes, and content slots.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bundle_version = models.ForeignKey(
        BlockBundleVersion,
        on_delete=models.CASCADE,
        related_name='block_definitions'
    )
    block_type_id = models.CharField(
        max_length=100,
        help_text='Unique identifier for this block type (e.g., "hero-banner", "feature-grid")'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    icon = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Lucide icon name for the block type'
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Category for grouping blocks in the editor'
    )
    variants = JSONField(
        default=list,
        blank=True,
        help_text='Array of variant objects: [{"id": "left", "name": "Left Aligned", "preview_image": "..."}]'
    )
    feature_toggles = JSONField(
        default=list,
        blank=True,
        help_text='Array of toggle definitions: [{"id": "show_cta", "name": "Show CTA", "default": true}]'
    )
    style_axes = JSONField(
        default=dict,
        blank=True,
        help_text='Style options: {"padding": ["sm", "md", "lg"], "theme": ["light", "dark"]}'
    )
    content_slots = JSONField(
        default=list,
        blank=True,
        help_text='Content slot schemas: [{"id": "title", "type": "text", "required": true, "max_length": 100}]'
    )
    defaults = JSONField(
        default=dict,
        blank=True,
        help_text='Default values for variants, toggles, styles, and content'
    )
    preview_template = models.TextField(
        blank=True,
        default='',
        help_text='Optional HTML template for editor preview'
    )
    metadata = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('category', 'name')
        unique_together = (('bundle_version', 'block_type_id'),)
        indexes = [
            models.Index(fields=['bundle_version', 'block_type_id']),
            models.Index(fields=['bundle_version', 'category']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.block_type_id})"

    def get_variant(self, variant_id: str) -> dict | None:
        """Get a variant definition by ID."""
        for variant in self.variants:
            if variant.get('id') == variant_id:
                return variant
        return None

    def get_toggle(self, toggle_id: str) -> dict | None:
        """Get a toggle definition by ID."""
        for toggle in self.feature_toggles:
            if toggle.get('id') == toggle_id:
                return toggle
        return None

    def get_slot(self, slot_id: str) -> dict | None:
        """Get a content slot schema by ID."""
        for slot in self.content_slots:
            if slot.get('id') == slot_id:
                return slot
        return None

    def validate_variant(self, variant_id: str) -> bool:
        """Check if a variant ID is valid for this block type."""
        if not self.variants:
            return True
        return any(v.get('id') == variant_id for v in self.variants)

    def validate_toggles(self, toggle_values: dict) -> list[str]:
        """Validate toggle values. Returns list of invalid toggle IDs."""
        valid_ids = {t.get('id') for t in self.feature_toggles}
        return [k for k in toggle_values.keys() if k not in valid_ids]

    def validate_styles(self, style_values: dict) -> list[str]:
        """Validate style values. Returns list of error messages."""
        errors = []
        for axis, value in style_values.items():
            if axis not in self.style_axes:
                errors.append(f"Unknown style axis: {axis}")
            elif value not in self.style_axes.get(axis, []):
                errors.append(f"Invalid value '{value}' for style axis '{axis}'")
        return errors

    def validate_content(self, content: dict) -> list[str]:
        """Validate content against slot schemas. Returns list of error messages."""
        errors = []
        for slot in self.content_slots:
            slot_id = slot.get('id')
            slot_type = slot.get('type', 'text')
            required = slot.get('required', False)
            max_length = slot.get('max_length')
            min_length = slot.get('min_length')

            value = content.get(slot_id)

            if required and (value is None or value == ''):
                errors.append(f"Required content slot '{slot_id}' is missing")
                continue

            if value is not None and slot_type == 'text':
                if not isinstance(value, str):
                    errors.append(f"Content slot '{slot_id}' must be a string")
                else:
                    if max_length and len(value) > max_length:
                        errors.append(f"Content slot '{slot_id}' exceeds max length of {max_length}")
                    if min_length and len(value) < min_length:
                        errors.append(f"Content slot '{slot_id}' is below min length of {min_length}")

        return errors


class BundleInstall(TenantScopedModel):
    """
    Tracks which bundle versions are installed for each tenant.
    Only one version of a bundle can be active per tenant at a time.
    """

    class InstallStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='bundle_installs'
    )
    bundle_version = models.ForeignKey(
        BlockBundleVersion,
        on_delete=models.CASCADE,
        related_name='installations'
    )
    status = models.CharField(
        max_length=20,
        choices=InstallStatus.choices,
        default=InstallStatus.ACTIVE
    )
    installed_at = models.DateTimeField(auto_now_add=True)
    installed_by = models.ForeignKey(
        'portal.MoioUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bundle_installations'
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    metadata = JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-installed_at',)
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'bundle_version']),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.nombre} - {self.bundle_version}"

    def clean(self):
        if self.status == self.InstallStatus.ACTIVE:
            existing_active = BundleInstall.objects.filter(
                tenant=self.tenant,
                bundle_version__bundle=self.bundle_version.bundle,
                status=self.InstallStatus.ACTIVE
            ).exclude(id=self.id).first()
            if existing_active:
                raise ValidationError({
                    'bundle_version': f'Tenant already has an active installation of bundle {self.bundle_version.bundle.name}'
                })

        if self.bundle_version.status != BlockBundleVersion.VersionStatus.PUBLISHED:
            raise ValidationError({
                'bundle_version': 'Only published bundle versions can be installed'
            })

    def save(self, *args, **kwargs):
        if self.status == self.InstallStatus.ACTIVE and not self.activated_at:
            self.activated_at = timezone.now()
        self.full_clean()
        super().save(*args, **kwargs)


class PageVersion(TenantScopedModel):
    """
    Immutable snapshot of a page at publish time.
    Stores the complete composition state for historical reference.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='page_versions'
    )
    page = models.ForeignKey(
        FluidPage,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.PositiveIntegerField()
    composition = JSONField(
        default=dict,
        help_text='Full page state snapshot including all blocks and their content'
    )
    content_pins = JSONField(
        default=dict,
        blank=True,
        help_text='Pinned content reference versions at publish time'
    )
    published_by = models.ForeignKey(
        'portal.MoioUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='published_page_versions'
    )
    published_at = models.DateTimeField(auto_now_add=True)
    metadata = JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-version_number',)
        unique_together = (('page', 'version_number'),)
        indexes = [
            models.Index(fields=['page', 'version_number']),
            models.Index(fields=['tenant', 'published_at']),
        ]

    def __str__(self) -> str:
        return f"{self.page.slug} v{self.version_number}"

    def clean(self):
        if self.page.tenant != self.tenant:
            raise ValidationError({
                'page': 'Page version must belong to the same tenant as the page'
            })

    def save(self, *args, **kwargs):
        if not self.version_number:
            last_version = PageVersion.objects.filter(
                page=self.page
            ).order_by('-version_number').first()
            self.version_number = (last_version.version_number + 1) if last_version else 1

        if not self.tenant_id:
            self.tenant = self.page.tenant

        self.full_clean()
        super().save(*args, **kwargs)
