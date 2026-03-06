"""
Core models for the communications app.
"""

from .message import Message, MessageContent, MessageType, ChannelType
from .channel import ChannelConfig

__all__ = [
    'Message',
    'MessageContent',
    'MessageType',
    'ChannelType',
    'ChannelConfig',
]