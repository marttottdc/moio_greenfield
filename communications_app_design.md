# Communications App - Arquitectura de Canales Refactorizada

## 📋 Resumen Ejecutivo

Este documento describe la refactorización completa de la arquitectura de canales de la aplicación actualmente llamada "chatbot". El objetivo es crear una arquitectura escalable, mantenible y extensible que soporte comunicación multi-canal con o sin integración de IA.

**Nombre Propuesto:** `communications` (en lugar de `chatbot`)

## 🚨 Problemas de la Arquitectura Actual

### 1. Duplicación Masiva de Código
- **6 handlers separados** con lógica duplicada (~200 líneas cada uno)
- **Funciones específicas por canal** que no pueden reutilizarse
- **Lógica hardcodeada** dispersa en templates y eventos

### 2. Alto Acoplamiento
- Funciones que esperan tipos específicos (`WhatsappMessage`)
- Dependencias directas entre componentes
- Cambios requieren modificaciones en cascada

### 3. Falta de Abstracción
- No hay interfaces comunes para canales
- No hay modelo unificado de mensaje
- Procesamiento específico por canal sin reutilización

### 4. Escalabilidad Limitada
- Añadir nuevo canal requiere desarrollo desde cero
- Features comunes no se pueden extender fácilmente
- Testing complejo y duplicado

## 🏗️ Arquitectura Propuesta

### Patrón Core: Strategy + Factory

```
communications/
├── core/
│   ├── strategies/
│   │   ├── base.py              # ChannelStrategy (ABC)
│   │   ├── whatsapp.py          # WhatsAppChannelStrategy
│   │   ├── instagram.py         # InstagramChannelStrategy
│   │   ├── messenger.py         # MessengerChannelStrategy
│   │   ├── email.py             # EmailChannelStrategy
│   │   └── web.py               # WebChannelStrategy
│   ├── models/
│   │   ├── message.py           # Message, MessageContent
│   │   └── channel.py           # ChannelConfig, ChannelType
│   ├── processor.py             # ChannelProcessor (orquestador)
│   └── factory.py               # ChannelFactory
├── handlers/
│   ├── webhook_handler.py       # Handler unificado
│   └── message_processor.py     # Procesador de mensajes AI
├── integrations/
│   ├── whatsapp/
│   ├── email/
│   ├── instagram/
│   └── messenger/
└── tasks.py                     # Tareas Celery unificadas
```

## 📋 Interfaces y Modelos

### 1. ChannelStrategy (Abstract Base Class)

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..models import Message

class ChannelStrategy(ABC):
    """Strategy abstracta para manejo de canales"""

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """Tipo de canal (whatsapp, email, instagram, etc.)"""
        pass

    @abstractmethod
    def parse_webhook(self, webhook_data: Dict[str, Any]) -> Optional[Message]:
        """Parse webhook data into unified Message object"""
        pass

    @abstractmethod
    def send_message(self, message: Message, recipient: str) -> bool:
        """Send message through channel"""
        pass

    @abstractmethod
    def mark_as_read(self, message_id: str) -> bool:
        """Mark message as read (if supported)"""
        pass

    @abstractmethod
    def download_media(self, media_id: str) -> Optional[str]:
        """Download media file (if supported)"""
        pass

    @abstractmethod
    def get_channel_config(self) -> Dict[str, Any]:
        """Get channel-specific configuration"""
        pass
```

### 2. Message Model (Unificado)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

class MessageType(Enum):
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

@dataclass
class MessageContent:
    type: MessageType
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_id: Optional[str] = None
    caption: Optional[str] = None
    location: Optional[Dict[str, float]] = None
    contacts: Optional[List[Dict[str, Any]]] = None
    interactive_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class Message:
    id: str
    channel: str
    sender: str
    recipient: Optional[str] = None
    content: MessageContent
    timestamp: datetime
    context_id: Optional[str] = None  # For threading/replies
    is_from_me: bool = False
    metadata: Optional[Dict[str, Any]] = None
```

### 3. ChannelFactory

```python
from typing import Dict, Type
from .strategies.base import ChannelStrategy
from .strategies import (
    WhatsAppChannelStrategy,
    InstagramChannelStrategy,
    MessengerChannelStrategy,
    EmailChannelStrategy,
    WebChannelStrategy
)

class ChannelFactory:
    """Factory para crear estrategias de canal"""

    _strategies: Dict[str, Type[ChannelStrategy]] = {
        'whatsapp': WhatsAppChannelStrategy,
        'instagram': InstagramChannelStrategy,
        'messenger': MessengerChannelStrategy,
        'email': EmailChannelStrategy,
        'web': WebChannelStrategy,
        'desktop': WebChannelStrategy,  # Reuse web strategy
    }

    @classmethod
    def get_strategy(cls, channel_type: str) -> ChannelStrategy:
        """Get channel strategy instance"""
        strategy_class = cls._strategies.get(channel_type.lower())
        if not strategy_class:
            raise ValueError(f"Unsupported channel type: {channel_type}")

        # Get tenant config and create strategy instance
        from django.conf import settings
        # Implementation depends on how config is stored

        return strategy_class()

    @classmethod
    def supported_channels(cls) -> List[str]:
        """Get list of supported channels"""
        return list(cls._strategies.keys())
```

### 4. ChannelProcessor (Orquestador)

```python
from typing import Dict, Any, Optional
from .models import Message
from .strategies.base import ChannelStrategy
from .factory import ChannelFactory
from ..ai import AIProcessor

class ChannelProcessor:
    """Procesador unificado de canales"""

    def __init__(self, channel_type: str, tenant_config: Dict[str, Any]):
        self.channel_type = channel_type
        self.strategy = ChannelFactory.get_strategy(channel_type)
        self.ai_processor = AIProcessor(tenant_config)
        self.tenant_config = tenant_config

    def process_webhook(self, webhook_data: Dict[str, Any]) -> Optional[Message]:
        """Process incoming webhook and return unified message"""
        try:
            # 1. Parse webhook using channel strategy
            message = self.strategy.parse_webhook(webhook_data)

            if not message:
                return None

            # 2. Mark as read if supported
            if hasattr(self.strategy, 'mark_as_read') and message.id:
                self.strategy.mark_as_read(message.id)

            # 3. Process with AI if configured
            if self._should_process_with_ai(message):
                response = self.ai_processor.process_message(message)
                if response:
                    self.strategy.send_message(response, message.sender)

            return message

        except Exception as e:
            # Log error and handle gracefully
            self._log_error("webhook_processing", str(e), webhook_data)
            return None

    def send_message(self, message: Message, recipient: str) -> bool:
        """Send message through channel"""
        try:
            return self.strategy.send_message(message, recipient)
        except Exception as e:
            self._log_error("message_send", str(e), {
                'message': message.__dict__,
                'recipient': recipient
            })
            return False

    def _should_process_with_ai(self, message: Message) -> bool:
        """Determine if message should be processed with AI"""
        # Check tenant configuration, human mode, etc.
        return True  # Simplified

    def _log_error(self, operation: str, error: str, data: Dict[str, Any]):
        """Log errors with context"""
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Channel processing error in {operation}: {error}", extra={
            'channel': self.channel_type,
            'operation': operation,
            'data': data
        })
```

## 🔧 Implementaciones Específicas

### WhatsApp Strategy Example

```python
from .base import ChannelStrategy
from ..models import Message, MessageContent, MessageType
from integrations.whatsapp.client import WhatsAppClient

class WhatsAppChannelStrategy(ChannelStrategy):

    @property
    def channel_type(self) -> str:
        return 'whatsapp'

    def parse_webhook(self, webhook_data: Dict[str, Any]) -> Optional[Message]:
        # Parse WhatsApp webhook format to unified Message
        # Handle messages, statuses, etc.
        pass

    def send_message(self, message: Message, recipient: str) -> bool:
        # Convert unified Message to WhatsApp format and send
        pass

    def mark_as_read(self, message_id: str) -> bool:
        # Mark WhatsApp message as read
        pass

    def download_media(self, media_id: str) -> Optional[str]:
        # Download WhatsApp media
        pass
```

### Email Strategy Example

```python
from .base import ChannelStrategy
from integrations.email.client import EmailClient

class EmailChannelStrategy(ChannelStrategy):

    @property
    def channel_type(self) -> str:
        return 'email'

    def parse_webhook(self, webhook_data: Dict[str, Any]) -> Optional[Message]:
        # Parse email webhook to unified Message
        # This would be called from email ingestion tasks
        pass

    def send_message(self, message: Message, recipient: str) -> bool:
        # Send email using SMTP/IMAP
        pass
```

## 🔄 Handler Unificado

### Webhook Handler

```python
# tasks.py
from communications.core.processor import ChannelProcessor

@shared_task(bind=True, queue='communications')
def unified_webhook_handler(self, channel_type: str, webhook_data: Dict[str, Any]):
    """Unified webhook handler for all channels"""

    task_id = current_task.request.id
    logger.info(f'Processing {channel_type} webhook: {task_id}')

    try:
        # Get tenant config (implementation depends on your setup)
        tenant_config = get_tenant_config_from_webhook(webhook_data)

        # Create processor and process
        processor = ChannelProcessor(channel_type, tenant_config)
        message = processor.process_webhook(webhook_data)

        if message:
            # Store message, emit events, etc.
            store_message(message)
            emit_communication_event(message)

        return {'status': 'success', 'message_id': message.id if message else None}

    except Exception as e:
        logger.error(f'Error processing {channel_type} webhook: {str(e)}')
        return {'status': 'error', 'error': str(e)}
```

### URL Configuration

```python
# urls.py
from communications.handlers import unified_webhook_handler

urlpatterns = [
    # Unified webhook endpoint for all channels
    path('webhooks/<str:channel_type>/', unified_webhook_handler, name='unified_webhook'),

    # Legacy endpoints (redirect to unified during migration)
    path('webhooks/whatsapp/', lambda r: redirect_to_unified(r, 'whatsapp')),
    path('webhooks/instagram/', lambda r: redirect_to_unified(r, 'instagram')),
    # ...
]
```

## 🤖 Integración con IA

### AI Processor

```python
from communications.ai import AIProcessor

class AIProcessor:
    """Handles AI processing for messages"""

    def __init__(self, tenant_config: Dict[str, Any]):
        self.config = tenant_config
        self.conversation_handler = tenant_config.get('conversation_handler', 'CHATBOT')

    def process_message(self, message: Message) -> Optional[Message]:
        """Process message with appropriate AI handler"""

        if self.conversation_handler == 'AGENT':
            return self._process_with_agent(message)
        elif self.conversation_handler == 'ASSISTANT':
            return self._process_with_assistant(message)
        elif self.conversation_handler == 'CHATBOT':
            return self._process_with_chatbot(message)
        else:
            return None

    def _process_with_agent(self, message: Message) -> Optional[Message]:
        # Use agent system
        pass

    def _process_with_assistant(self, message: Message) -> Optional[Message]:
        # Use OpenAI Assistant
        pass

    def _process_with_chatbot(self, message: Message) -> Optional[Message]:
        # Use legacy chatbot
        pass
```

## 📋 Plan de Migración

### Fase 1: Preparación (1 semana)
1. ✅ Crear estructura de directorios nueva
2. ✅ Implementar interfaces base (`ChannelStrategy`, `Message`)
3. ✅ Crear `ChannelFactory` básico
4. ✅ Tests unitarios para interfaces

### Fase 2: WhatsApp Strategy (2 semanas)
1. ✅ Implementar `WhatsAppChannelStrategy`
2. ✅ Migrar lógica de `whatsapp_webhook_handler`
3. ✅ Testing completo de WhatsApp
4. ✅ Actualizar URLs para usar handler unificado

### Fase 3: Email Strategy (1 semana)
1. ✅ Implementar `EmailChannelStrategy`
2. ✅ Completar funcionalidad de envío de email
3. ✅ Testing de email
4. ✅ Migrar `handle_received_email`

### Fase 4: Otros Canales (2 semanas)
1. ✅ Implementar `InstagramChannelStrategy`
2. ✅ Implementar `MessengerChannelStrategy`
3. ✅ Implementar `WebChannelStrategy`
4. ✅ Testing de todos los canales

### Fase 5: Limpieza (1 semana)
1. ✅ Remover código legacy
2. ✅ Actualizar documentación
3. ✅ Testing de integración completo
4. ✅ Despliegue y monitoreo

## 📈 Beneficios Esperados

### Mantenibilidad
- **1 handler** unificado vs 6 separados
- Lógica común centralizada
- Interfaces claras y documentadas

### Escalabilidad
- Añadir canal = implementar 1 strategy
- Reutilización completa de lógica
- Testing simplificado

### Extensibilidad
- Nuevos canales sin modificar código existente
- Features comunes aplican automáticamente
- Arquitectura abierta a extensiones

### Performance
- Menos duplicación de código
- Mejor separación de responsabilidades
- Más fácil de optimizar y cachear

## 🔍 Consideraciones Técnicas

### Compatibilidad
- Mantener compatibilidad con webhooks existentes durante migración
- Gradual rollout con feature flags
- Rollback plan completo

### Error Handling
- Logging unificado por canal
- Métricas por canal y operación
- Circuit breakers para integraciones externas

### Seguridad
- Validación de webhooks por canal
- Rate limiting por canal
- Encriptación de credenciales

### Testing
- Unit tests para cada strategy
- Integration tests unificados
- End-to-end tests por canal

## 🎯 Conclusión

Esta refactorización transforma una arquitectura problemática en una solución escalable y mantenible. El patrón Strategy permite extender fácilmente nuevos canales mientras mantiene la lógica común centralizada.

**Tiempo estimado:** 7 semanas
**Riesgo:** Medio (migración gradual)
**Beneficio:** Alto (arquitectura sostenible a largo plazo)