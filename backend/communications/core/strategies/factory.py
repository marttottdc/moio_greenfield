"""
Channel Factory for creating channel strategies.

This factory provides a centralized way to create and manage
channel strategies for all supported communication platforms.
"""

from typing import Dict, Type, Optional, List
from ..models import ChannelType, ChannelConfig
from .base import ChannelStrategy


class ChannelFactory:
    """
    Factory for creating channel strategy instances.

    This class manages the registration and creation of channel strategies,
    providing a clean interface for getting the appropriate strategy for each channel.
    """

    _strategies: Dict[ChannelType, Type[ChannelStrategy]] = {}

    @classmethod
    def register_strategy(cls, channel_type: ChannelType, strategy_class: Type[ChannelStrategy]):
        """
        Register a strategy class for a channel type.

        Args:
            channel_type: The channel type
            strategy_class: The strategy class to register
        """
        cls._strategies[channel_type] = strategy_class

    @classmethod
    def get_strategy(cls, channel_type: ChannelType) -> ChannelStrategy:
        """
        Get a strategy instance for the given channel type.

        Args:
            channel_type: The channel type

        Returns:
            ChannelStrategy instance

        Raises:
            ValueError: If no strategy is registered for the channel type
        """
        strategy_class = cls._strategies.get(channel_type)
        if not strategy_class:
            raise ValueError(f"No strategy registered for channel type: {channel_type.value}")

        return strategy_class()

    @classmethod
    def get_supported_channels(cls) -> List[ChannelType]:
        """
        Get list of all supported channel types.

        Returns:
            List of supported ChannelType enums
        """
        return list(cls._strategies.keys())

    @classmethod
    def is_channel_supported(cls, channel_type: ChannelType) -> bool:
        """
        Check if a channel type is supported.

        Args:
            channel_type: The channel type to check

        Returns:
            True if supported, False otherwise
        """
        return channel_type in cls._strategies

    @classmethod
    def create_from_config(cls, config: ChannelConfig) -> ChannelStrategy:
        """
        Create a strategy instance from a channel configuration.

        Args:
            config: Channel configuration

        Returns:
            ChannelStrategy instance configured for the channel
        """
        strategy = cls.get_strategy(config.channel_type)
        # Here we could pass configuration to the strategy if needed
        return strategy

    @classmethod
    def get_channel_info(cls, channel_type: ChannelType, config: Optional[ChannelConfig] = None) -> Dict:
        """
        Get information about a channel type.

        Args:
            channel_type: The channel type
            config: Optional channel configuration

        Returns:
            Dictionary with channel information
        """
        try:
            strategy = cls.get_strategy(channel_type)
            info = strategy.get_channel_info(config) if config else {}
            return {
                "channel_type": channel_type.value,
                "supported": True,
                "info": info,
            }
        except ValueError:
            return {
                "channel_type": channel_type.value,
                "supported": False,
                "info": {},
            }

    @classmethod
    def validate_channel_config(cls, config: ChannelConfig) -> Dict[str, Any]:
        """
        Validate a channel configuration.

        Args:
            config: Channel configuration to validate

        Returns:
            Dictionary with validation results
        """
        try:
            strategy = cls.get_strategy(config.channel_type)
            is_valid = strategy.validate_config(config)
            return {
                "valid": is_valid,
                "channel_type": config.channel_type.value,
                "message": "Configuration is valid" if is_valid else "Configuration is invalid",
            }
        except ValueError as e:
            return {
                "valid": False,
                "channel_type": config.channel_type.value,
                "message": f"Unsupported channel type: {str(e)}",
            }
        except Exception as e:
            return {
                "valid": False,
                "channel_type": config.channel_type.value,
                "message": f"Validation error: {str(e)}",
            }


# Initialize with placeholder strategies (to be implemented)
# This allows the factory to work even before specific strategies are implemented
class PlaceholderStrategy(ChannelStrategy):
    """Placeholder strategy for channels not yet implemented."""

    def __init__(self, channel_type: ChannelType):
        self._channel_type = channel_type

    @property
    def channel_type(self) -> ChannelType:
        return self._channel_type

    def validate_config(self, config: ChannelConfig) -> bool:
        return False

    def parse_webhook(self, webhook_data: Dict[str, Any], config: ChannelConfig) -> Optional[Message]:
        return None

    def send_message(self, message: Message, config: ChannelConfig) -> bool:
        return False


# Register placeholder strategies for all channel types initially
for channel_type in ChannelType:
    ChannelFactory.register_strategy(channel_type, lambda ct=channel_type: PlaceholderStrategy(ct))