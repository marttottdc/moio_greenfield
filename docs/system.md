# System Documentation

## Purpose

Multi-tenant platform providing CRM, automation workflows, AI-powered chatbots, recruitment management, e-commerce, and content management capabilities.

## High-Level Architecture

### Core Components

- **portal**: Multi-tenant foundation (Tenant, MoioUser, TenantConfiguration)
- **crm**: Customer relationship management (Contact, Ticket, Deal, Product, Pipeline)
- **chatbot**: AI-powered conversational agents (ChatbotSession, AgentConfiguration, WhatsApp/Instagram/Messenger integration)
- **flows**: Workflow automation engine (Flow, FlowVersion, FlowExecution, FlowSchedule, FlowSignalTrigger)
- **campaigns**: Marketing campaign management (Campaign, Audience, CampaignData)
- **datalab**: Data processing and analytics (FileAsset, DataSource, ResultSet, Pipeline, Import)
- **recruiter**: Recruitment/ATS functionality (Candidate, JobPosting, Employee)
- **fluidcms**: Content management system (FluidPage, FluidBlock, FluidMedia, Article)
- **fluidcommerce**: E-commerce (Product, ProductVariant, Category, Order)
- **assessments**: Surveys/quizzes (AssessmentCampaign, AssessmentQuestion, AssessmentInstance)
- **fam**: Fixed asset management (FamLabel, AssetRecord, AssetDelegation)
- **moio_calendar**: Calendar and booking (CalendarEvent, AvailabilitySlot, BookingType)
- **security**: Service-to-service authentication (ServiceToken)
- **resources**: Shared API resources (WhatsApp templates, agent tools)
- **websockets_app**: Real-time WebSocket consumers

### Technology Stack

- Django 5.x with Django REST Framework
- PostgreSQL with pgvector extension
- Redis for caching (cacheops) and Celery broker
- Celery for async task processing
- Django Channels for WebSockets
- AWS S3 for media/static storage
- JWT authentication (SimpleJWT)

### URL Routing Structure

- `/webhooks/` - External webhook receivers (WhatsApp, Instagram, Messenger)
- `/api/v1/` - Public REST API
- `/api/schema/`, `/api/docs/`, `/api/redoc/` - OpenAPI documentation
- `/admin/` - Django admin
- `/accounts/` - allauth authentication
- Application-specific routes under i18n patterns

## Global Invariants

### Tenant Isolation

- All tenant-scoped models inherit from `TenantScopedModel`
- `TenantManager` filters querysets by `current_tenant` context variable
- `TenantMiddleware` sets tenant context from authenticated user

### Authentication

- JWT tokens with tenant-aware serializer (`TenantJWTAAuthentication`)
- Service tokens for service-to-service calls (`ServiceJWTAuthentication`)
- 60-minute access token lifetime, 7-day refresh token lifetime

### Unique Constraints

- Contact phone and email unique per tenant
- Flow names unique per tenant
- Pipeline names unique per tenant
- Agent names unique per tenant
- Dataset names unique per tenant

## Versioning Policy

- FlowVersion: Single incrementing version number per flow with FSM lifecycle (draft → testing → published → archived)
- FlowScriptVersion: Version numbers per script with publish mechanism
- DatasetVersion: Sequential version numbers per dataset
- BlockBundleVersion: Semantic versioning with lifecycle states (draft → submitted → published → deprecated)
- PageVersion: Auto-incrementing version per page

## Installed Applications

```
assessments
campaigns
chatbot
crm
datalab
fam
flows
fluidcms
fluidcommerce
moio_calendar
portal
recruiter
security
websockets_app
```

## Queue Configuration

- `default` - Standard tasks
- `flows` - Flow execution and script tasks (`flows.tasks.*`, `datalab.scripts.*`, `datalab.pipelines.*`)
- Priority queues: HIGH, MEDIUM, LOW (prefixed by APP_NAME)
