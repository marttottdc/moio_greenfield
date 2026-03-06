"""
Channel strategies for different communication platforms.

Each strategy implements the ChannelStrategy interface to provide
unified behavior across all supported channels.
"""

from .base import ChannelStrategy
from .factory import ChannelFactory

__all__ = [
    'ChannelStrategy',
    'ChannelFactory',
]