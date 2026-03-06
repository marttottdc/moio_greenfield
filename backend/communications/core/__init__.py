"""
Core components of the communications app.
"""

from .models import Message, MessageContent, MessageType, ChannelType, ChannelConfig
from .strategies import ChannelStrategy, ChannelFactory
from .processor import ChannelProcessor

__all__ = [
    'Message',
    'MessageContent',
    'MessageType',
    'ChannelType',
    'ChannelConfig',
    'ChannelStrategy',
    'ChannelFactory',
    'ChannelProcessor',
]