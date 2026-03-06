"""
Communications App

Multi-channel communication platform with AI integration.

Features:
- Multi-channel support (WhatsApp, Email, Instagram, Messenger, Web, Desktop)
- AI-powered conversation handling
- Unified message processing
- Extensible channel architecture

Architecture:
- Strategy Pattern for channel implementations
- Factory Pattern for channel creation
- Unified Message model across all channels
"""

__version__ = '1.0.0'
__author__ = 'Moio Platform'

default_app_config = 'communications.apps.CommunicationsConfig'