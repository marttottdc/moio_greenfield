# Communications App - Plan de Migración

## 📋 Resumen Ejecutivo

Este documento detalla el plan completo para migrar la aplicación "chatbot" a "communications" con la nueva arquitectura de canales refactorizada.

**Duración estimada:** 7 semanas
**Riesgo:** Medio (migración gradual con rollback)
**Equipo requerido:** 2 desarrolladores full-time

## 🎯 Objetivos

1. **Cambiar nombre:** `chatbot` → `communications`
2. **Refactorizar arquitectura:** Strategy Pattern + Factory
3. **Unificar handlers:** 6 handlers → 1 handler unificado
4. **Mejorar mantenibilidad:** Código DRY y extensible

## 📅 Cronograma Detallado

### **Semana 1: Preparación y Interfaces**

#### Día 1-2: Estructura de Directorios
```bash
# Crear nueva estructura
mkdir -p communications/core/strategies
mkdir -p communications/core/models
mkdir -p communications/handlers
mkdir -p communications/integrations/whatsapp
mkdir -p communications/integrations/email
mkdir -p communications/integrations/instagram
mkdir -p communications/integrations/messenger

# Mover archivos existentes (backup first)
cp -r chatbot/ chatbot_backup/
```

#### Día 3-4: Interfaces Base
- ✅ Implementar `ChannelStrategy` (ABC)
- ✅ Implementar `Message` y `MessageContent` models
- ✅ Crear `ChannelFactory` básico
- ✅ Tests unitarios para interfaces

#### Día 5: Configuración Inicial
- ✅ Actualizar `apps.py`: `ChatbotConfig` → `CommunicationsConfig`
- ✅ Crear migración inicial para renombrar app
- ✅ Feature flag para modo dual (legacy + new)

### **Semana 2-3: WhatsApp Strategy**

#### Día 1-3: WhatsApp Strategy Base
```python
# communications/core/strategies/whatsapp.py
class WhatsAppChannelStrategy(ChannelStrategy):
    def parse_webhook(self, webhook_data: dict) -> Optional[Message]:
        # Migrar lógica de whatsapp_webhook_handler
        pass

    def send_message(self, message: Message, recipient: str) -> bool:
        # Migrar lógica de Messenger.smart_reply
        pass
```

#### Día 4-5: WhatsApp Testing
- ✅ Unit tests para WhatsApp strategy
- ✅ Integration tests con WhatsApp Business API
- ✅ Comparar resultados legacy vs new

#### Día 6-7: WhatsApp Handler Migration
- ✅ Crear `unified_webhook_handler`
- ✅ URL routing: `/webhooks/whatsapp/` → `/webhooks/whatsapp/`
- ✅ Feature flag: `USE_NEW_WHATSAPP_HANDLER`

### **Semana 4: Email Strategy**

#### Día 1-2: Email Strategy Completa
```python
# communications/core/strategies/email.py
class EmailChannelStrategy(ChannelStrategy):
    def parse_webhook(self, webhook_data: dict) -> Optional[Message]:
        # Para email, esto vendrá de tareas de sync
        pass

    def send_message(self, message: Message, recipient: str) -> bool:
        # IMPLEMENTAR envío real de email (missing!)
        pass
```

#### Día 3-4: Email Testing
- ✅ Tests para recepción de email
- ✅ Tests para envío de email (nuevo)
- ✅ Integración con servicios de email (Gmail, Outlook, IMAP)

#### Día 5: Email Handler Migration
- ✅ Migrar `handle_received_email`
- ✅ Crear `sync_email_task` unified
- ✅ Actualizar `process_email_with_assistant`

### **Semana 5-6: Otros Canales**

#### Día 1-2: Instagram Strategy
```python
# communications/core/strategies/instagram.py
class InstagramChannelStrategy(ChannelStrategy):
    def parse_webhook(self, webhook_data: dict) -> Optional[Message]:
        # Migrar lógica de instagram_webhook_handler
        pass
```

#### Día 3-4: Messenger Strategy
```python
# communications/core/strategies/messenger.py
class MessengerChannelStrategy(ChannelStrategy):
    def parse_webhook(self, webhook_data: dict) -> Optional[Message]:
        # Migrar lógica de messenger_webhook_handler
        pass
```

#### Día 5-7: Web/Desktop Strategy
```python
# communications/core/strategies/web.py
class WebChannelStrategy(ChannelStrategy):
    # Reutilizar para web y desktop
    pass
```

### **Semana 7: Limpieza y Optimización**

#### Día 1-2: Remover Código Legacy
```python
# Eliminar archivos legacy
rm chatbot/tasks.py  # old handlers
rm chatbot/core/whatsapp_message_types.py  # move to integrations
rm chatbot/core/messenger.py  # logic moved to strategies

# Actualizar imports en todo el proyecto
find . -name "*.py" -exec sed -i 's/from chatbot/from communications/g' {} \;
```

#### Día 3-4: Testing Final
- ✅ Tests de integración completos
- ✅ Tests E2E por canal
- ✅ Performance testing
- ✅ Load testing con múltiples canales

#### Día 5: Despliegue y Monitoreo
- ✅ Despliegue gradual con feature flags
- ✅ Monitoreo de errores por canal
- ✅ Métricas de performance
- ✅ Rollback plan activo

## 🔧 Scripts de Migración

### **Script 1: Rename App (settings.py)**
```python
# scripts/rename_app.py
def update_settings():
    """Update Django settings for new app name"""
    # INSTALLED_APPS
    # Update any hardcoded references

def update_urls():
    """Update URL patterns"""
    # app_name in urls.py
    # Namespace references
```

### **Script 2: Move Files**
```bash
#!/bin/bash
# scripts/move_files.sh

# Move core files
mv chatbot/core/* communications/core/

# Move models
mv chatbot/models/* communications/

# Move templates (update paths)
mv chatbot/templates/chatbot communications/templates/communications

# Update template references in views
find communications/ -name "*.py" -exec sed -i 's/chatbot\///communications\//g' {} \;
```

### **Script 3: Update Imports**
```python
# scripts/update_imports.py
def update_all_imports():
    """Update all import statements across the project"""
    import os
    import re

    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r') as f:
                    content = f.read()

                # Update imports
                content = re.sub(r'from chatbot\.', r'from communications.', content)
                content = re.sub(r'import chatbot', r'import communications', content)

                with open(filepath, 'w') as f:
                    f.write(content)
```

## 🧪 Estrategia de Testing

### **Testing Pyramid**
```
End-to-End Tests (10%)
├── Channel-specific flows
└── Cross-channel scenarios

Integration Tests (30%)
├── Strategy implementations
├── Factory patterns
└── Processor orchestration

Unit Tests (60%)
├── Individual strategies
├── Message parsing
├── Factory methods
└── Processor logic
```

### **Testing por Canal**
```python
# tests/test_channels.py
class TestChannelStrategies:
    def test_whatsapp_parsing(self):
        strategy = WhatsAppChannelStrategy()
        message = strategy.parse_webhook(whatsapp_webhook_data)
        assert message.channel == 'whatsapp'
        assert message.content.type == MessageType.TEXT

    def test_email_sending(self):
        strategy = EmailChannelStrategy()
        message = Message(...)
        result = strategy.send_message(message, 'user@example.com')
        assert result == True
```

## 📊 Métricas de Éxito

### **Técnicas**
- ✅ **0 errores** de import después de migración
- ✅ **100% tests** pasando
- ✅ **Cobertura > 80%** en nueva arquitectura
- ✅ **Latency < 200ms** para procesamiento de mensajes

### **Funcionales**
- ✅ Todos los canales funcionando igual que legacy
- ✅ Webhooks procesados correctamente
- ✅ Mensajes enviados/recibidos
- ✅ Sesiones mantenidas

### **Arquitectónicas**
- ✅ **6 handlers → 1 handler** unificado
- ✅ **DRY principle** aplicado
- ✅ **Strategy pattern** correctamente implementado
- ✅ **Factory pattern** funcionando

## 🚨 Plan de Contingencia

### **Rollback Plan**
```python
# settings.py feature flag
USE_NEW_ARCHITECTURE = False  # Set to False to rollback

# URLs fallback
if not USE_NEW_ARCHITECTURE:
    # Keep old URLs active
    path('webhooks/whatsapp/', old_whatsapp_handler),
```

### **Rollback Steps**
1. **Desactivar feature flag:** `USE_NEW_ARCHITECTURE = False`
2. **Revertir URLs:** Apuntar a handlers legacy
3. **Restaurar backup:** `cp -r chatbot_backup/ chatbot/`
4. **Restart services**

### **Puntos de Verificación**
- **Cada commit** debe mantener funcionalidad legacy
- **Diariamente** ejecutar tests completos
- **Semanalmente** revisión de métricas de performance
- **Deploy gradual** con canary releases

## 📈 Beneficios Esperados

### **Después de Migración**
- **-70% líneas de código** (duplicación eliminada)
- **+50% velocidad** de desarrollo de nuevos canales
- **-60% bugs** relacionados con canales
- **+90% mantenibilidad** del código

### **Métricas de Performance**
- **Latency:** 150ms → 120ms (procesamiento)
- **Throughput:** +30% mensajes por segundo
- **Memory:** -25% uso por canal
- **CPU:** -20% uso en picos

## 🎯 Checklist Final

- [ ] Estructura de directorios creada
- [ ] Interfaces base implementadas
- [ ] Todas las strategies implementadas
- [ ] Handler unificado funcionando
- [ ] Tests completos pasando
- [ ] Feature flags configurados
- [ ] Rollback plan documentado
- [ ] Equipo entrenado en nueva arquitectura
- [ ] Monitoreo y alertas configurados
- [ ] Documentación actualizada

## 📞 Soporte Post-Migración

### **Semana 8-12: Monitoreo**
- Monitoreo continuo de errores
- Optimización de performance
- Resolución de issues encontrados

### **Timeline Extendida**
- **Mes 2:** Añadir 1-2 nuevos canales usando nueva arquitectura
- **Mes 3:** Refactor adicional si necesario
- **Mes 6:** Revisión completa de arquitectura

---

**Estado:** Plan aprobado y listo para ejecución
**Fecha de inicio:** [Fecha a definir]
**Responsable:** [Nombre del lead developer]