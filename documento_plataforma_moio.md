# 📋 Documento Descriptivo - Plataforma MOIO

## 🎯 **Visión General de la Plataforma**

**MOIO** es una plataforma CRM/ERP multi-tenant avanzada construida sobre Django, que combina capacidades de Inteligencia Artificial, automatización de workflows y comunicaciones multi-canal. Diseñada para empresas que buscan digitalizar sus operaciones comerciales y de atención al cliente, ofrece una solución completa y escalable para gestión de relaciones con clientes, marketing, reclutamiento, e-commerce y más.

### **Características Principales**
- **🏢 Arquitectura Multi-tenant**: Aislamiento completo de datos por organización
- **🤖 Integración Avanzada de IA**: GPT-4, Claude, embeddings vectoriales, agentes conversacionales
- **⚡ Automatización Visual**: Motor de workflows con scripting Python integrado
- **📱 Comunicaciones Multi-canal**: WhatsApp, Instagram, Messenger, Email, Web Chat
- **📊 Analytics y BI**: Procesamiento de datos avanzado con DataLab
- **🛒 E-commerce Integrado**: Plataforma de comercio electrónico con WooCommerce
- **📅 Gestión de Calendario**: Sistema de reservas y eventos
- **💼 ATS Completo**: Sistema de reclutamiento y seguimiento de candidatos

---

## 🏗️ **Arquitectura y Stack Tecnológico**

### **Backend Principal**
- **Framework**: Django 5.0.11
- **Base de Datos**: PostgreSQL con extensión pgvector para búsqueda vectorial
- **Cache/Message Broker**: Redis
- **Task Queue**: Celery 5.4.0
- **WebSockets**: Django Channels 4.1.0
- **API Framework**: Django REST Framework 3.16.0

### **Integraciones de IA**
- **OpenAI GPT**: Modelos GPT-4 para agentes conversacionales
- **Anthropic Claude**: API de Claude para procesamiento avanzado
- **Cohere**: Embeddings y procesamiento de lenguaje natural
- **Mistral AI**: Modelos alternativos de IA
- **Hugging Face Transformers**: Modelos de ML personalizados

### **Integraciones Externas**
- **WhatsApp Business API**: Mensajería empresarial
- **Facebook/Instagram APIs**: Integración con redes sociales
- **MercadoPago**: Procesamiento de pagos
- **WooCommerce**: Comercio electrónico
- **Google Maps**: Servicios de geolocalización
- **AWS S3**: Almacenamiento de archivos

### **Infraestructura**
- **Servidor Web**: Hypercorn (ASGI) + Gunicorn (WSGI)
- **Contenedor**: Docker
- **Despliegue**: Heroku-style con Procfile
- **Monitoreo**: Health checks, logging con Logtail

---

## 📦 **Módulos Principales**

### **1. 🏢 Portal - Fundación Multi-tenant**
**Ubicación**: `portal/`  
**Responsabilidad**: Infraestructura base y autenticación multi-tenant

#### **Funcionalidades**
- Sistema de tenants con aislamiento completo de datos
- Autenticación JWT multi-tenant
- Gestión de usuarios y permisos granulares
- Configuración específica por organización
- API keys para acceso automatizado
- Middleware para contexto de tenant

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/users/` - CRUD completo de usuarios por tenant
- `POST /api/v1/tenants/self-provision/` - Auto-provisioning de tenants
- `GET /api/v1/health/` - Health check del sistema
- `GET /api/schema/` - Esquema OpenAPI completo
- `GET /api/docs/` - Interfaz Swagger UI

#### **Funciones de negocio**
- Gestión multi-tenant completa con aislamiento de datos
- Autenticación JWT tenant-aware
- Sistema de permisos granulares por usuario
- Configuraciones específicas por organización
- API keys para acceso automatizado

#### **Integraciones**
- WhatsApp Business API
- Facebook/Instagram APIs
- MercadoPago para pagos
- WooCommerce para e-commerce
- Google Maps para geolocalización
- AWS S3 para almacenamiento

#### **Webhooks/Triggers**
- Facebook OAuth callbacks
- Instagram OAuth callbacks
- WhatsApp Business API webhooks
- MercadoPago payment notifications

#### **Procesos asíncronos**
- Procesamiento de webhooks entrantes
- Sincronización de datos externos
- Limpieza automática de sesiones expiradas

#### **Permisos/ACL**
- Sistema de capabilities (users_manage, tenant_admin, etc.)
- Roles jerárquicos por tenant
- Permisos granulares por funcionalidad
- Autenticación multi-nivel (JWT, API keys, sesiones)

#### **Validaciones**
- Validación de dominios por tenant
- Límites de recursos por organización
- Validación de configuraciones específicas
- Reglas de seguridad para API keys

#### **Métricas/Reportes**
- Health checks con métricas de sistema
- Logs centralizados con Logtail
- Monitoreo de rendimiento por tenant
- Estadísticas de uso de recursos

#### **Modelos Principales**
- `Tenant`: Configuración por organización
- `MoioUser`: Usuarios del sistema
- `TenantConfiguration`: Configuraciones específicas
- `UserApiKey`: Claves de API

---

### **2. 📞 CRM - Customer Relationship Management**
**Ubicación**: `crm/`  
**Responsabilidad**: Gestión completa de relaciones con clientes

#### **Funcionalidades**
- Gestión avanzada de contactos y empresas
- Sistema de tickets para soporte al cliente
- Pipeline de ventas con deals y oportunidades
- Catálogo de productos con variantes
- Base de conocimientos integrada
- Seguimiento de actividades y timeline
- Sistema de etiquetado y segmentación
- Gestión de inventario básico

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/contacts/` - Gestión completa de contactos
- `GET/POST /api/v1/tickets/` - Sistema de tickets de soporte
- `GET/POST /api/v1/deals/` - Pipeline de ventas
- `GET/POST /api/v1/products/` - Catálogo de productos
- `GET/POST /api/v1/activities/` - Timeline de interacciones
- `GET/POST /api/v1/tags/` - Sistema de etiquetado
- `GET/POST /api/v1/knowledge/` - Base de conocimientos

#### **Funciones de negocio**
- Gestión avanzada de contactos (leads, clientes, empresas)
- Sistema de tickets con asignación y seguimiento
- Pipeline de ventas con etapas configurables
- Catálogo de productos con variantes
- Seguimiento de actividades e interacciones
- Base de conocimientos integrada
- Sistema de etiquetado y segmentación

#### **Integraciones**
- WhatsApp Business API para mensajería
- MercadoPago para procesamiento de pagos
- WooCommerce para sincronización de productos
- Calendarios externos (Google Calendar, Outlook)
- Sistemas de email (SMTP/IMAP)

#### **Webhooks/Triggers**
- Eventos de contacto (created, updated, deleted)
- Eventos de ticket (status_changed, assigned)
- Eventos de deal (stage_changed, won, lost)
- Eventos de actividad (contact_interaction)
- Eventos de pago (payment_received, payment_failed)

#### **Procesos asíncronos**
- Sincronización de listas de bloqueo de WhatsApp
- Procesamiento de actividades en masa
- Generación de reportes automáticos
- Limpieza de datos antiguos

#### **Permisos/ACL**
- Permisos por contacto (view, edit, delete)
- Permisos por ticket (assign, close, escalate)
- Permisos por deal (view_pipeline, manage_deals)
- Permisos por producto (manage_catalog)
- Control de acceso basado en jerarquía organizacional

#### **Validaciones**
- Validación de formatos de contacto (email, teléfono E164)
- Reglas de negocio para pipelines de ventas
- Validaciones de inventario por producto
- Restricciones de estado de tickets
- Validaciones de campos personalizados

#### **Métricas/Reportes**
- Dashboard de KPIs de ventas
- Reportes de conversión por fuente
- Estadísticas de tickets por agente
- Análisis de productos más vendidos
- Métricas de satisfacción del cliente

#### **Modelos Principales**
- `Contact`: Información de contactos
- `Company`: Datos empresariales
- `Ticket`: Sistema de soporte
- `Deal`: Pipeline de ventas
- `Product`: Catálogo de productos
- `ActivityRecord`: Historial de interacciones
- `KnowledgeItem`: Base de conocimientos

---

### **3. 🤖 Communications - Sistema de Comunicaciones Refactorizado**
**Ubicación**: `chatbot/` → `communications/` (en refactorización)  
**Estado**: En proceso de refactorización completa siguiendo patrón Strategy

#### **Funcionalidades**
- Agentes conversacionales impulsados por IA
- Integración multi-canal (WhatsApp, Email, Instagram, Messenger)
- Sesiones de conversación persistentes
- Templates de WhatsApp Business API
- Sistema de respuestas inteligentes (smart replies)
- Manejo de contexto conversacional
- Web chat integrado

#### **APIs/Endpoints disponibles**
- `POST /api/v1/webhooks/<channel_type>/` - Webhook unificado por canal
- `GET/POST /api/v1/communications/sessions/` - Gestión de sesiones
- `GET/POST /api/v1/whatsapp/templates/` - Templates de WhatsApp
- `GET/POST /api/v1/email/accounts/` - Cuentas de email

#### **Funciones de negocio**
- Agentes conversacionales impulsados por IA
- Comunicación multi-canal (WhatsApp, Email, Instagram, Messenger, Web)
- Sesiones de conversación persistentes
- Templates de mensajes personalizables
- Sistema de respuestas inteligentes
- Manejo de contexto conversacional
- Web chat integrado

#### **Integraciones**
- WhatsApp Business API
- Facebook Messenger API
- Instagram Business API
- Servicios de email (SMTP/IMAP)
- OpenAI GPT para agentes IA
- Anthropic Claude para procesamiento avanzado

#### **Webhooks/Triggers**
- Webhooks de mensajes entrantes por canal
- Eventos de estado de mensajes
- Eventos de sesión (created, closed)
- Eventos de agente (response_generated)
- Eventos de error de integración

#### **Procesos asíncronos**
- Procesamiento de webhooks con Celery
- Generación de respuestas IA
- Envío masivo de mensajes
- Sincronización de templates
- Limpieza de sesiones inactivas

#### **Permisos/ACL**
- Permisos por canal (send_messages, manage_templates)
- Control de acceso a agentes IA
- Permisos de configuración por tenant
- Restricciones de mensajería masiva

#### **Validaciones**
- Validación de formatos de mensaje por canal
- Límites de tamaño de archivos multimedia
- Validación de números de teléfono E164
- Reglas de frecuencia de mensajes
- Validaciones de templates de WhatsApp

#### **Métricas/Reportes**
- Estadísticas de mensajes por canal
- Métricas de respuesta de agentes IA
- Reportes de entregabilidad de mensajes
- Análisis de conversaciones por tema
- Dashboard de rendimiento de comunicaciones

#### **Modelos Principales**
- `AgentConfiguration`: Configuración de agentes IA
- `ChatbotSession`: Sesiones de conversación
- `WaMessageLog`: Log de mensajes WhatsApp
- `EmailAccount`: Cuentas de email

#### **Refactorización Planificada**
- Implementación del patrón Strategy para canales
- Unificación de handlers duplicados
- Arquitectura más mantenible y extensible

---

### **4. ⚙️ Flows - Motor de Automatización**
**Ubicación**: `flows/`  
**Responsabilidad**: Automatización visual de workflows

#### **Funcionalidades**
- Editor visual de workflows (drag & drop)
- Scripting Python integrado y seguro
- Versionado de flujos (draft → testing → published)
- Ejecución programada y basada en eventos
- Integración con APIs externas
- Manejo de contexto y variables persistentes
- Triggers basados en señales del sistema

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/flows/` - Gestión de flujos
- `GET/POST /api/v1/flows/<id>/executions/` - Ejecuciones de flujos
- `GET/POST /api/v1/flows/schedules/` - Programación de flujos
- `GET/POST /api/v1/flows/events/` - Definiciones de eventos
- `GET/POST /api/v1/flows/scheduled-tasks/` - Tareas programadas

#### **Funciones de negocio**
- Editor visual de workflows drag & drop
- Scripting Python integrado y seguro
- Versionado de flujos (draft → testing → published)
- Ejecución programada y basada en eventos
- Integración con APIs externas
- Manejo de contexto y variables persistentes
- Triggers basados en señales del sistema

#### **Integraciones**
- APIs REST externas
- Bases de datos externas
- Servicios de email
- WhatsApp Business API
- Servicios de pago
- Sistemas CRM externos

#### **Webhooks/Triggers**
- Triggers basados en eventos del sistema
- Webhooks de ejecución de flujos
- Eventos de cambio de estado de flujo
- Notificaciones de error en ejecución
- Eventos de schedule (started, completed, failed)

#### **Procesos asíncronos**
- Ejecución de flujos con Celery
- Procesamiento de schedules
- Ejecución de tareas programadas
- Limpieza de ejecuciones antiguas
- Reintentos automáticos de fallos

#### **Permisos/ACL**
- Permisos de edición de flujos
- Control de ejecución de flujos
- Acceso a variables de contexto
- Permisos de scheduling
- Control de visibilidad de flujos

#### **Validaciones**
- Validación de sintaxis Python en scripts
- Validaciones de estructura de flujo
- Límites de ejecución por tenant
- Validaciones de parámetros de entrada
- Reglas de seguridad en código Python

#### **Métricas/Reportes**
- Estadísticas de ejecución de flujos
- Métricas de rendimiento por nodo
- Reportes de errores de flujo
- Análisis de uso de recursos
- Dashboard de automatización

#### **Modelos Principales**
- `Flow`: Definición de flujo
- `FlowVersion`: Versionado de flujos
- `FlowExecution`: Ejecuciones de flujos
- `FlowScript`: Scripts Python embebidos
- `FlowSchedule`: Programación de flujos

---

### **5. 📢 Campaigns - Campañas de Marketing**
**Ubicación**: `campaigns/`  
**Responsabilidad**: Gestión de campañas de marketing

#### **Funcionalidades**
- Creación y gestión de campañas de marketing
- Segmentación avanzada de audiencias
- Integración con WhatsApp Business API
- Templates de mensajes personalizables
- Seguimiento de métricas de campaña
- Automatización de envíos masivos

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/campaigns/` - Gestión de campañas
- `GET/POST /api/v1/campaigns/<id>/audiences/` - Segmentación de audiencias
- `GET/POST /api/v1/campaigns/metrics/` - Métricas de campaña

#### **Funciones de negocio**
- Creación y gestión de campañas de marketing
- Segmentación avanzada de audiencias
- Integración con WhatsApp Business API
- Templates de mensajes personalizables
- Seguimiento de métricas de campaña
- Automatización de envíos masivos

#### **Integraciones**
- WhatsApp Business API
- Servicios de email marketing
- Plataformas de SMS
- Sistemas de CRM para segmentación

#### **Webhooks/Triggers**
- Eventos de campaña (started, completed)
- Notificaciones de métricas actualizadas
- Eventos de segmentación completada

#### **Procesos asíncronos**
- Envío masivo de mensajes con Celery
- Procesamiento de métricas de campaña
- Actualización de segmentaciones

#### **Permisos/ACL**
- Permisos de creación de campañas
- Control de acceso a audiencias
- Permisos de envío masivo
- Acceso a métricas de campaña

#### **Validaciones**
- Límites de tamaño de audiencias
- Validaciones de templates
- Restricciones de frecuencia de envío
- Validaciones de contenido de mensajes

#### **Métricas/Reportes**
- Estadísticas de entregabilidad
- Tasas de apertura y conversión
- Análisis de rendimiento por canal
- Reportes de ROI de campañas

#### **Modelos Principales**
- `Campaign`: Definición de campaña
- `Audience`: Segmentación de audiencia
- `CampaignData`: Datos y métricas de campaña

---

### **6. 📊 DataLab - Procesamiento de Datos**
**Ubicación**: `datalab/`  
**Responsabilidad**: ETL, análisis y procesamiento de datos

#### **Funcionalidades**
- Upload y gestión de archivos (Excel, CSV, PDF)
- Procesamiento ETL avanzado
- Datasets versionados con control de cambios
- Pipelines de transformación visuales
- Análisis y visualización de datos
- Integración bidireccional con CRM
- Procesamiento de imágenes con OCR

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/datalab/files/` - Gestión de archivos
- `GET/POST /api/v1/datalab/datasets/` - Conjuntos de datos
- `GET/POST /api/v1/datalab/panels/` - Paneles de visualización
- `POST /api/v1/datalab/execute/` - Ejecución de análisis
- `GET/POST /api/v1/datalab/data-sources/` - Fuentes de datos externas

#### **Funciones de negocio**
- Upload y gestión de archivos (Excel, CSV, PDF)
- Procesamiento ETL avanzado
- Datasets versionados con control de cambios
- Pipelines de transformación visuales
- Análisis y visualización de datos
- Integración bidireccional con CRM
- Procesamiento de imágenes con OCR

#### **Integraciones**
- Fuentes de datos externas (APIs, bases de datos)
- Servicios de OCR para documentos
- Motores de análisis de datos
- Sistemas de visualización (Chart.js, D3.js)
- Exportación a múltiples formatos

#### **Webhooks/Triggers**
- Eventos de procesamiento completado
- Notificaciones de error en ETL
- Eventos de dataset actualizado
- Triggers de re-procesamiento automático

#### **Procesos asíncronos**
- Procesamiento ETL con Celery
- Generación de visualizaciones
- Exportación de datasets grandes
- Limpieza automática de archivos temporales
- Reindexación de datos

#### **Permisos/ACL**
- Control de acceso a datasets
- Permisos de ejecución de análisis
- Control de exportación de datos
- Acceso a paneles de visualización
- Permisos de gestión de fuentes de datos

#### **Validaciones**
- Validación de formatos de archivo
- Límites de tamaño de upload
- Validaciones de estructura de datos
- Reglas de calidad de datos
- Validaciones de permisos de acceso

#### **Métricas/Reportes**
- Estadísticas de procesamiento ETL
- Métricas de calidad de datos
- Reportes de uso de almacenamiento
- Análisis de rendimiento de queries
- Dashboard de DataLab

#### **Modelos Principales**
- `FileAsset`: Archivos subidos al sistema
- `DataSource`: Fuentes de datos externas
- `ResultSet`: Resultados procesados
- `Dataset`: Conjuntos de datos versionados
- `Pipeline`: Pipelines de procesamiento

---

### **7. 👥 Recruiter - Sistema de Reclutamiento**
**Ubicación**: `recruiter/`  
**Responsabilidad**: Applicant Tracking System (ATS)

#### **Funcionalidades**
- Gestión completa de candidatos y CVs
- Publicación de ofertas de trabajo
- Evaluación y scoring automático de candidatos
- Seguimiento del proceso de selección
- Integración con plataformas de reclutamiento externas
- Reportes de reclutamiento

#### **APIs/Endpoints disponibles**
- `GET/POST /recruiter/candidates/` - Gestión de candidatos
- `GET/POST /recruiter/job_posting/` - Ofertas de trabajo
- `GET/POST /recruiter/dashboard/` - Dashboard de reclutamiento
- `POST /recruiter/webhooks/psigma/` - Webhooks de plataforma externa

#### **Funciones de negocio**
- Gestión completa de candidatos y CVs
- Publicación y gestión de ofertas de trabajo
- Evaluación y scoring automático de candidatos
- Seguimiento del proceso de selección
- Reportes de reclutamiento detallados
- Gestión de empleados internos

#### **Integraciones**
- Plataformas de reclutamiento externas (Psigma)
- Servicios de análisis de CV
- APIs de LinkedIn para reclutamiento
- Servicios de verificación de antecedentes
- Sistemas de calendario para entrevistas

#### **Webhooks/Triggers**
- Webhooks de plataforma de reclutamiento
- Eventos de candidato (applied, evaluated)
- Notificaciones de nueva oferta
- Eventos de cambio de estado en proceso
- Triggers de evaluación automática

#### **Procesos asíncronos**
- Procesamiento de CVs masivos
- Evaluación automática de candidatos
- Sincronización con plataformas externas
- Generación de reportes programados
- Envío de notificaciones a candidatos

#### **Permisos/ACL**
- Permisos de gestión de ofertas
- Control de acceso a candidatos
- Permisos de evaluación y scoring
- Acceso a reportes de reclutamiento
- Control de publicación de ofertas

#### **Validaciones**
- Validación de formatos de CV
- Reglas de proceso de selección
- Validaciones de datos de candidato
- Límites de ofertas por recruiter
- Validaciones de etapas de selección

#### **Métricas/Reportes**
- Estadísticas de contratación
- Métricas de tiempo de contratación
- Reportes de fuentes de candidatos
- Análisis de conversión por oferta
- Dashboard de KPIs de reclutamiento

#### **Modelos Principales**
- `Candidate`: Información de candidatos
- `JobPosting`: Ofertas de trabajo
- `Employee`: Empleados de la organización
- `CandidateEvaluation`: Evaluaciones y scoring

---

### **8. 📄 FluidCMS - Content Management System**
**Ubicación**: `fluidcms/`  
**Responsabilidad**: Gestión de contenido web

#### **Funcionalidades**
- Sistema de páginas dinámicas
- Bloques de contenido reutilizables
- Gestión de artículos y publicaciones
- Versionado de contenido
- Sistema de bundles para plantillas
- Editor visual de contenido

#### **Modelos Principales**
- `FluidPage`: Páginas de contenido
- `FluidBlock`: Bloques reutilizables
- `Article`: Artículos y publicaciones
- `BlockBundle`: Paquetes de bloques

---

### **9. 🛒 FluidCommerce - Plataforma E-commerce**
**Ubicación**: `fluidcommerce/`  
**Responsabilidad**: Comercio electrónico integrado

#### **Funcionalidades**
- Catálogo de productos con variantes (tallas, colores, etc.)
- Gestión completa de pedidos y fulfillment
- Categorización jerárquica de productos
- Integración nativa con WooCommerce
- Gestión de inventario en tiempo real
- Sistema de precios dinámicos

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/commerce/products/` - Gestión de productos
- `GET/POST /api/v1/commerce/orders/` - Pedidos y fulfillment
- `GET/POST /api/v1/commerce/categories/` - Categorización de productos
- `GET/POST /api/v1/commerce/inventory/` - Gestión de inventario

#### **Funciones de negocio**
- Catálogo de productos con variantes (tallas, colores, etc.)
- Gestión completa de pedidos y fulfillment
- Categorización jerárquica de productos
- Integración nativa con WooCommerce
- Gestión de inventario en tiempo real
- Sistema de precios dinámicos

#### **Integraciones**
- WooCommerce API
- MercadoPago para pagos
- Sistemas de envío y logística
- Plataformas de marketplace
- Sistemas de contabilidad

#### **Webhooks/Triggers**
- Eventos de pedido (created, paid, shipped)
- Notificaciones de inventario bajo
- Eventos de producto (updated, discontinued)
- Webhooks de WooCommerce

#### **Procesos asíncronos**
- Sincronización con WooCommerce
- Procesamiento de pedidos masivos
- Actualización automática de inventario
- Cálculos de precios dinámicos

#### **Permisos/ACL**
- Permisos de gestión de catálogo
- Control de acceso a pedidos
- Permisos de modificación de precios
- Acceso a reportes de ventas

#### **Validaciones**
- Validaciones de estructura de productos
- Reglas de inventario (stock mínimo)
- Validaciones de precios y descuentos
- Restricciones de pedidos por cliente

#### **Métricas/Reportes**
- Reportes de ventas por producto
- Análisis de conversión de carrito
- Estadísticas de fulfillment
- Dashboards de rendimiento e-commerce

#### **Modelos Principales**
- `Product`: Productos del catálogo
- `ProductVariant`: Variantes de producto
- `Order`: Pedidos y transacciones
- `Category`: Categorías de productos

---

### **10. 📝 Assessments - Sistema de Evaluaciones**
**Ubicación**: `assessments/`  
**Responsabilidad**: Encuestas y evaluaciones

#### **Funcionalidades**
- Creación de encuestas y cuestionarios
- Distribución masiva a audiencias
- Análisis avanzado de resultados
- Integración con flujos de trabajo
- Reportes y dashboards de resultados

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/assessments/` - Gestión de encuestas
- `GET/POST /api/v1/assessments/<id>/questions/` - Preguntas del cuestionario
- `GET/POST /api/v1/assessments/instances/` - Instancias de evaluación
- `GET/POST /api/v1/assessments/results/` - Resultados y análisis

#### **Funciones de negocio**
- Creación de encuestas y cuestionarios
- Distribución masiva a audiencias
- Análisis avanzado de resultados
- Integración con flujos de trabajo
- Reportes y dashboards de resultados

#### **Integraciones**
- Sistemas de distribución de encuestas
- Plataformas de análisis de datos
- Flujos de trabajo para automatización
- Dashboards de visualización

#### **Webhooks/Triggers**
- Eventos de evaluación completada
- Notificaciones de nuevos resultados
- Triggers de análisis automático

#### **Procesos asíncronos**
- Procesamiento de respuestas masivas
- Generación de análisis estadísticos
- Envío de recordatorios automáticos

#### **Permisos/ACL**
- Permisos de creación de encuestas
- Control de distribución a audiencias
- Acceso a resultados individuales
- Permisos de análisis y reportes

#### **Validaciones**
- Validaciones de estructura de cuestionarios
- Límites de tiempo de evaluación
- Reglas de obligatoriedad de preguntas
- Validaciones de formato de respuestas

#### **Métricas/Reportes**
- Estadísticas de completitud
- Análisis de tendencias en respuestas
- Reportes de satisfacción
- Dashboards interactivos de resultados

#### **Modelos Principales**
- `AssessmentCampaign`: Campañas de evaluación
- `AssessmentQuestion`: Preguntas del cuestionario
- `AssessmentInstance`: Instancias individuales

---

### **11. 🏷️ FAM - Fixed Asset Management**
**Ubicación**: `fam/`  
**Responsabilidad**: Gestión de activos fijos

#### **Funcionalidades**
- Etiquetado y tracking de activos físicos
- Gestión de inventario de activos
- Sistema de delegación y préstamos
- Reportes de activos y depreciación
- Integración con códigos QR

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/fam/assets/` - Gestión de activos
- `GET/POST /api/v1/fam/labels/` - Etiquetas QR
- `GET/POST /api/v1/fam/delegations/` - Sistema de préstamos
- `GET/POST /api/v1/fam/reports/` - Reportes de depreciación

#### **Funciones de negocio**
- Etiquetado y tracking de activos físicos
- Gestión de inventario de activos
- Sistema de delegación y préstamos
- Reportes de activos y depreciación
- Integración con códigos QR

#### **Integraciones**
- Sistemas de escaneo QR
- Plataformas de inventario externas
- Sistemas contables para depreciación
- Calendarios para recordatorios de mantenimiento

#### **Webhooks/Triggers**
- Eventos de activo (created, moved, delegated)
- Notificaciones de depreciación
- Alertas de mantenimiento programado

#### **Procesos asíncronos**
- Cálculos de depreciación automática
- Generación de reportes programados
- Sincronización con sistemas externos

#### **Permisos/ACL**
- Permisos de gestión de activos
- Control de delegación de activos
- Acceso a reportes de depreciación
- Permisos de creación de etiquetas

#### **Validaciones**
- Validaciones de códigos de activo
- Reglas de depreciación por tipo
- Límites de delegación por usuario
- Validaciones de ubicación física

#### **Métricas/Reportes**
- Reportes de depreciación acumulada
- Estadísticas de uso de activos
- Análisis de eficiencia de inventario
- Dashboards de activos por ubicación

#### **Modelos Principales**
- `FamLabel`: Etiquetas de identificación
- `AssetRecord`: Registros de activos
- `AssetDelegation`: Delegación de activos

---

### **12. 📅 Moio Calendar - Sistema de Calendario**
**Ubicación**: `moio_calendar/`  
**Responsabilidad**: Gestión de eventos y reservas

#### **Funcionalidades**
- Gestión de calendario y eventos
- Sistema de reservas y citas
- Slots de disponibilidad configurables
- Integración con otros módulos del sistema
- Sincronización con calendarios externos

#### **APIs/Endpoints disponibles**
- `GET/POST /api/v1/calendar/events/` - Gestión de eventos
- `GET/POST /api/v1/calendar/bookings/` - Sistema de reservas
- `GET/POST /api/v1/calendar/availability/` - Slots de disponibilidad
- `GET/POST /api/v1/calendar/types/` - Tipos de reserva

#### **Funciones de negocio**
- Gestión de calendario y eventos
- Sistema de reservas y citas
- Slots de disponibilidad configurables
- Integración con otros módulos del sistema
- Sincronización con calendarios externos

#### **Integraciones**
- Google Calendar API
- Outlook Calendar
- Sistemas de CRM para contactos
- WhatsApp para notificaciones
- Sistemas de email para recordatorios

#### **Webhooks/Triggers**
- Eventos de reserva (created, confirmed, cancelled)
- Notificaciones de eventos próximos
- Recordatorios automáticos
- Eventos de cambio de disponibilidad

#### **Procesos asíncronos**
- Envío de recordatorios automáticos
- Sincronización con calendarios externos
- Procesamiento de reservas masivas
- Limpieza de eventos antiguos

#### **Permisos/ACL**
- Permisos de creación de eventos
- Control de reservas por tipo
- Acceso a calendarios de otros usuarios
- Permisos de modificación de disponibilidad

#### **Validaciones**
- Validaciones de conflictos de horario
- Reglas de disponibilidad por tipo
- Límites de duración de eventos
- Validaciones de capacidad máxima

#### **Métricas/Reportes**
- Estadísticas de ocupación de calendario
- Reportes de reservas por tipo
- Análisis de puntualidad
- Dashboards de disponibilidad

#### **Modelos Principales**
- `CalendarEvent`: Eventos del calendario
- `AvailabilitySlot`: Slots de disponibilidad
- `BookingType`: Tipos de reserva

---

### **13. 🔐 Security - Autenticación de Servicios**
**Ubicación**: `security/`  
**Responsabilidad**: Autenticación service-to-service

#### **Funcionalidades**
- JWT para comunicación segura entre servicios
- Gestión de tokens de servicio
- Autenticación de APIs internas
- Control de acceso basado en roles

#### **APIs/Endpoints disponibles**
- `POST /api/v1/security/auth/` - Autenticación de servicios
- `GET/POST /api/v1/security/tokens/` - Gestión de tokens JWT
- `GET/POST /api/v1/security/permissions/` - Control de permisos

#### **Funciones de negocio**
- JWT para comunicación segura entre servicios
- Gestión de tokens de servicio
- Autenticación de APIs internas
- Control de acceso basado en roles

#### **Integraciones**
- Sistemas de autenticación externos
- Servicios de directorio (LDAP/Active Directory)
- APIs de identidad y acceso

#### **Webhooks/Triggers**
- Eventos de autenticación fallida
- Notificaciones de tokens expirados
- Eventos de cambio de permisos

#### **Procesos asíncronos**
- Rotación automática de tokens
- Limpieza de sesiones expiradas
- Auditoría de acceso

#### **Permisos/ACL**
- Control de acceso a servicios
- Gestión de roles y permisos
- Auditoría de operaciones
- Restricciones por IP/servicio

#### **Validaciones**
- Validación de tokens JWT
- Verificación de firmas
- Límites de tiempo de validez
- Validaciones de permisos

#### **Métricas/Reportes**
- Estadísticas de autenticación
- Reportes de intentos fallidos
- Análisis de uso de servicios
- Auditoría de seguridad

---

### **14. 🌐 WebSockets App - Comunicación en Tiempo Real**
**Ubicación**: `websockets_app/`  
**Responsabilidad**: Consumers WebSocket para comunicación en tiempo real

#### **Funcionalidades**
- Manejo de conexiones WebSocket
- Comunicación bidireccional en tiempo real
- Integración con el sistema de eventos
- Notificaciones push

#### **APIs/Endpoints disponibles**
- `WS /ws/notifications/` - Conexiones WebSocket
- `GET/POST /api/v1/ws/connections/` - Gestión de conexiones
- `POST /api/v1/ws/broadcast/` - Envío de notificaciones

#### **Funciones de negocio**
- Manejo de conexiones WebSocket
- Comunicación bidireccional en tiempo real
- Integración con el sistema de eventos
- Notificaciones push

#### **Integraciones**
- Django Channels para WebSockets
- Redis para backend de canales
- Sistema de eventos de la plataforma
- Notificaciones push móviles

#### **Webhooks/Triggers**
- Eventos de conexión WebSocket
- Notificaciones en tiempo real
- Eventos de sistema broadcast
- Triggers de desconexión automática

#### **Procesos asíncronos**
- Manejo de conexiones con Channels
- Procesamiento de mensajes en cola
- Limpieza de conexiones inactivas
- Reintentos de entrega de mensajes

#### **Permisos/ACL**
- Control de acceso a canales
- Permisos de envío de notificaciones
- Restricciones por tenant
- Límites de conexiones por usuario

#### **Validaciones**
- Validación de autenticación WebSocket
- Límites de mensajes por segundo
- Validaciones de formato de mensajes
- Restricciones de tamaño de payload

#### **Métricas/Reportes**
- Estadísticas de conexiones activas
- Métricas de latencia de mensajes
- Reportes de entregabilidad
- Análisis de uso de WebSockets

---

## 🏛️ **Patrones de Diseño y Arquitectura**

### **Patrones Arquitectónicos Implementados**

#### **Multi-tenancy Robusto**
- **TenantManager**: Manager personalizado para filtrado automático por tenant
- **TenantScopedModel**: Modelo base abstracto para aislamiento de datos
- **TenantMiddleware**: Middleware para contexto de tenant en requests
- **TenantJWTAuthentication**: Autenticación JWT consciente de tenants

#### **Strategy Pattern (En Desarrollo)**
- Implementado en el refactor del módulo de comunicaciones
- Estrategias específicas por canal (WhatsApp, Email, Instagram, Messenger)
- ChannelFactory para creación dinámica de estrategias

#### **Factory Pattern**
- **ChannelFactory**: Creación de estrategias de comunicación
- **IntegrationRegistry**: Registro de integraciones externas

#### **Observer Pattern**
- **Event System**: Sistema de eventos desacoplado
- **Signals**: Señales Django para comunicación entre módulos

#### **Repository Pattern**
- Managers personalizados con lógica de negocio encapsulada
- Querysets optimizados por tenant

### **Domain-Driven Design**
- **Bounded Contexts**: Módulos como contextos delimitados (CRM, Communications, Flows)
- **Aggregate Pattern**: Tenant como raíz de agregado
- **Value Objects**: Configuraciones JSON, embeddings vectoriales

---

## ⚙️ **Configuración y Despliegue**

### **Variables de Entorno Principales**
- `DATABASE_URL`: Conexión PostgreSQL
- `REDIS_URL`: Conexión Redis
- `SECRET_KEY`: Clave secreta Django
- `OPENAI_API_KEY`: API key de OpenAI
- `ANTHROPIC_API_KEY`: API key de Anthropic
- `WHATSAPP_API_KEY`: API key de WhatsApp Business

### **Configuración de Producción**
- **AWS S3**: Almacenamiento de archivos estáticos y media
- **Redis**: Cache y broker de tareas asíncronas
- **PostgreSQL con pgvector**: Base de datos con capacidades de búsqueda vectorial
- **Celery**: Procesamiento asíncrono con múltiples colas especializadas
- **Hypercorn**: Servidor ASGI de alto rendimiento

### **Monitoreo y Observabilidad**
- **Health Checks**: Endpoints dedicados para monitoreo
- **Logging**: Integración con Logtail para centralización de logs
- **Performance**: Métricas de latencia y rendimiento
- **Error Tracking**: Manejo centralizado de errores

---

## 🔄 **Desarrollo y Evolución**

### **Proyecto de Refactorización Activo**
El módulo `chatbot` está siendo completamente refactorizado al módulo `communications` siguiendo el patrón Strategy para mejorar mantenibilidad y escalabilidad.

**Beneficios Esperados:**
- Reducción del 70% en líneas de código
- Aumento del 50% en velocidad de desarrollo de nuevos canales
- Arquitectura más mantenible y extensible

### **Principios de Desarrollo**
- **SOLID Principles**: Diseño orientado a objetos robusto
- **DRY (Don't Repeat Yourself)**: Eliminación de duplicación de código
- **TDD/BDD**: Desarrollo guiado por pruebas
- **CI/CD**: Integración y despliegue continuo

---

## 📈 **Valor Estratégico**

MOIO representa una **plataforma enterprise-ready** que combina las mejores prácticas de desarrollo de software con funcionalidades avanzadas de IA y automatización. Está diseñada para:

- **Escalar** con el crecimiento del negocio
- **Integrar** múltiples sistemas y APIs externas
- **Automatizar** procesos complejos mediante workflows visuales
- **Analizar** datos para toma de decisiones inteligente
- **Comunicar** efectivamente con clientes a través de múltiples canales

La plataforma está posicionada como una solución completa para empresas que buscan transformar digitalmente sus operaciones comerciales y de atención al cliente, manteniendo altos estándares de calidad técnica y arquitectura moderna.

---

*Documento generado basado en análisis exhaustivo del repositorio MOIO - Última actualización: Marzo 2026 - Funciones específicas agregadas*