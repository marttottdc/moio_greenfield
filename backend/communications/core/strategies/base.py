"""
Base channel strategy interface.

All channel implementations must inherit from this abstract base class
to ensure consistent behavior across all communication platforms.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from ..models import Message, ChannelConfig, ChannelType


class ChannelStrategy(ABC):
    """
    Abstract base class for channel implementations.

    This interface defines the contract that all channel strategies must implement,
    ensuring consistent behavior across WhatsApp, Email, Instagram, etc.
    """

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType:
        """The type of channel this strategy handles."""
        pass

    @property
    def supported_message_types(self) -> List[str]:
        """List of supported message types for this channel."""
        return ["text"]  # Default to text-only

    @abstractmethod
    def validate_config(self, config: ChannelConfig) -> bool:
        """
        Validate that the channel configuration is complete and correct.

        Args:
            config: Channel configuration to validate

        Returns:
            True if configuration is valid, False otherwise
        """
        pass

    @abstractmethod
    def parse_webhook(self, webhook_data: Dict[str, Any], config: ChannelConfig) -> Optional[Message]:
        """
        Parse incoming webhook data into a unified Message object.

        Args:
            webhook_data: Raw webhook payload from the channel
            config: Channel configuration

        Returns:
            Parsed Message object or None if parsing fails
        """
        pass

    @abstractmethod
    def send_message(self, message: Message, config: ChannelConfig) -> bool:
        """
        Send a message through this channel.

        Args:
            message: Unified message to send
            config: Channel configuration

        Returns:
            True if message was sent successfully, False otherwise
        """
        pass

    def mark_as_read(self, message_id: str, config: ChannelConfig) -> bool:
        """
        Mark a message as read (if supported by the channel).

        Args:
            message_id: ID of the message to mark as read
            config: Channel configuration

        Returns:
            True if successful, False otherwise
        """
        # Default implementation - not all channels support this
        return False

    def download_media(self, media_id: str, config: ChannelConfig) -> Optional[str]:
        """
        Download media file from the channel (if supported).

        Args:
            media_id: ID of the media to download
            config: Channel configuration

        Returns:
            Local file path if successful, None otherwise
        """
        # Default implementation - not all channels support media
        return None

    def get_channel_info(self, config: ChannelConfig) -> Dict[str, Any]:
        """
        Get channel-specific information and capabilities.

        Args:
            config: Channel configuration

        Returns:
            Dictionary with channel information
        """
        return {
            "channel_type": self.channel_type.value,
            "supported_types": self.supported_message_types,
            "has_webhooks": True,
            "has_media": False,
            "has_read_receipts": False,
            "has_typing_indicators": False,
        }

    def validate_webhook_signature(self, payload: str, signature: str, config: ChannelConfig) -> bool:
        """
        Validate webhook signature for security (if supported).

        Args:
            payload: Raw webhook payload
            signature: Signature from webhook headers
            config: Channel configuration

        Returns:
            True if signature is valid, False otherwise
        """
        # Default implementation - most channels don't use signatures
        return True

    def get_webhook_url(self, config: ChannelConfig) -> Optional[str]:
        """
        Get the webhook URL for this channel.

        Args:
            config: Channel configuration

        Returns:
            Webhook URL or None
        """
        return config.webhook_url

    def setup_webhook(self, config: ChannelConfig) -> bool:
        """
        Setup webhook for the channel (if supported).

        Args:
            config: Channel configuration

        Returns:
            True if setup was successful
        """
        # Default implementation - manual setup required
        return False

    def test_connection(self, config: ChannelConfig) -> Dict[str, Any]:
        """
        Test the connection to the channel.

        Args:
            config: Channel configuration

        Returns:
            Dictionary with test results
        """
        try:
            is_valid = self.validate_config(config)
            return {
                "success": is_valid,
                "message": "Configuration valid" if is_valid else "Configuration invalid",
                "channel_type": self.channel_type.value,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection test failed: {str(e)}",
                "channel_type": self.channel_type.value,
            }