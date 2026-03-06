"""
Unified message models for all communication channels.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum


class MessageType(Enum):
    """Supported message content types across all channels."""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACTS = "contacts"
    INTERACTIVE = "interactive"
    REACTION = "reaction"
    ORDER = "order"
    UNKNOWN = "unknown"


class ChannelType(Enum):
    """Supported communication channels."""
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    INSTAGRAM = "instagram"
    MESSENGER = "messenger"
    WEB = "web"
    DESKTOP = "desktop"


@dataclass
class MessageContent:
    """
    Unified content structure for all message types.

    This class normalizes content from different channels into a consistent format.
    """
    type: MessageType
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_id: Optional[str] = None
    caption: Optional[str] = None
    location: Optional[Dict[str, float]] = None  # {"latitude": float, "longitude": float}
    contacts: List[Dict[str, Any]] = field(default_factory=list)
    interactive_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type.value,
            "text": self.text,
            "media_url": self.media_url,
            "media_id": self.media_id,
            "caption": self.caption,
            "location": self.location,
            "contacts": self.contacts,
            "interactive_data": self.interactive_data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageContent':
        """Create from dictionary."""
        return cls(
            type=MessageType(data["type"]),
            text=data.get("text"),
            media_url=data.get("media_url"),
            media_id=data.get("media_id"),
            caption=data.get("caption"),
            location=data.get("location"),
            contacts=data.get("contacts", []),
            interactive_data=data.get("interactive_data"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Message:
    """
    Unified message model for all communication channels.

    This is the core data structure that normalizes messages from all channels.
    """
    id: str
    channel: ChannelType
    sender: str
    content: MessageContent
    timestamp: datetime
    recipient: Optional[str] = None
    context_id: Optional[str] = None  # For threading/replies
    is_from_me: bool = False
    is_read: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization/storage."""
        return {
            "id": self.id,
            "channel": self.channel.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content.to_dict(),
            "timestamp": self.timestamp.isoformat(),
            "context_id": self.context_id,
            "is_from_me": self.is_from_me,
            "is_read": self.is_read,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            channel=ChannelType(data["channel"]),
            sender=data["sender"],
            recipient=data.get("recipient"),
            content=MessageContent.from_dict(data["content"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            context_id=data.get("context_id"),
            is_from_me=data.get("is_from_me", False),
            is_read=data.get("is_read", False),
            metadata=data.get("metadata", {}),
        )

    @property
    def is_media(self) -> bool:
        """Check if message contains media."""
        return self.content.type in [MessageType.IMAGE, MessageType.AUDIO, MessageType.VIDEO, MessageType.DOCUMENT]

    @property
    def has_text(self) -> bool:
        """Check if message has text content."""
        return bool(self.content.text and self.content.text.strip())

    def get_text_content(self) -> str:
        """Get text content, handling different message types."""
        if self.content.type == MessageType.TEXT:
            return self.content.text or ""
        elif self.is_media and self.content.caption:
            return self.content.caption
        elif self.content.type == MessageType.LOCATION:
            if self.content.location:
                lat, lng = self.content.location["latitude"], self.content.location["longitude"]
                return f"Location: {lat}, {lng}"
            return "Location shared"
        elif self.content.type == MessageType.CONTACTS:
            return f"Contacts shared: {len(self.content.contacts)}"
        else:
            return f"{self.content.type.value.title()} message"