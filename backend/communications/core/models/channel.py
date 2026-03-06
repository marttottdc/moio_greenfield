"""
Channel configuration models.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .message import ChannelType


@dataclass
class ChannelConfig:
    """
    Configuration for a communication channel.

    Contains all settings needed to interact with a specific channel.
    """
    channel_type: ChannelType
    tenant_id: str
    is_enabled: bool = True
    credentials: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)
    webhook_url: Optional[str] = None
    webhook_token: Optional[str] = None

    # WhatsApp specific
    whatsapp_business_account_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None

    # Email specific
    email_imap_server: Optional[str] = None
    email_smtp_server: Optional[str] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None  # Encrypted in production

    # Social media specific
    instagram_access_token: Optional[str] = None
    messenger_page_access_token: Optional[str] = None
    messenger_page_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "channel_type": self.channel_type.value,
            "tenant_id": self.tenant_id,
            "is_enabled": self.is_enabled,
            "credentials": self.credentials,
            "settings": self.settings,
            "webhook_url": self.webhook_url,
            "webhook_token": self.webhook_token,
            "whatsapp_business_account_id": self.whatsapp_business_account_id,
            "whatsapp_access_token": self.whatsapp_access_token,
            "whatsapp_phone_number_id": self.whatsapp_phone_number_id,
            "email_imap_server": self.email_imap_server,
            "email_smtp_server": self.email_smtp_server,
            "email_username": self.email_username,
            "email_password": self.email_password,
            "instagram_access_token": self.instagram_access_token,
            "messenger_page_access_token": self.messenger_page_access_token,
            "messenger_page_id": self.messenger_page_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChannelConfig':
        """Create from dictionary."""
        return cls(
            channel_type=ChannelType(data["channel_type"]),
            tenant_id=data["tenant_id"],
            is_enabled=data.get("is_enabled", True),
            credentials=data.get("credentials", {}),
            settings=data.get("settings", {}),
            webhook_url=data.get("webhook_url"),
            webhook_token=data.get("webhook_token"),
            whatsapp_business_account_id=data.get("whatsapp_business_account_id"),
            whatsapp_access_token=data.get("whatsapp_access_token"),
            whatsapp_phone_number_id=data.get("whatsapp_phone_number_id"),
            email_imap_server=data.get("email_imap_server"),
            email_smtp_server=data.get("email_smtp_server"),
            email_username=data.get("email_username"),
            email_password=data.get("email_password"),
            instagram_access_token=data.get("instagram_access_token"),
            messenger_page_access_token=data.get("messenger_page_access_token"),
            messenger_page_id=data.get("messenger_page_id"),
        )

    @property
    def is_configured(self) -> bool:
        """Check if channel is properly configured."""
        if not self.is_enabled:
            return False

        if self.channel_type == ChannelType.WHATSAPP:
            return bool(self.whatsapp_access_token and self.whatsapp_phone_number_id)

        elif self.channel_type == ChannelType.EMAIL:
            return bool(self.email_username and self.email_password and
                       self.email_imap_server and self.email_smtp_server)

        elif self.channel_type == ChannelType.INSTAGRAM:
            return bool(self.instagram_access_token)

        elif self.channel_type == ChannelType.MESSENGER:
            return bool(self.messenger_page_access_token and self.messenger_page_id)

        elif self.channel_type in [ChannelType.WEB, ChannelType.DESKTOP]:
            return True  # Web channels don't need external credentials

        return False