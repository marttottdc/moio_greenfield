# moio CRM Platform

## Overview
moio is a modern CRM platform for managing customer contacts, marketing campaigns, support tickets, and workflow automation. It aims to digitalize and optimize customer relationship processes, with a strong focus on WhatsApp communication and marketing automation. The platform is a full-stack TypeScript application featuring a React frontend and an Express backend. Its UI is inspired by Radiant design principles, incorporating BentoCard layouts and subtle gradients, designed for premium productivity. Key capabilities include comprehensive customer relationship management, marketing automation, and an integrated command center for natural language interaction. The business vision is to provide a powerful tool for businesses to enhance their customer engagement and operational efficiency.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
The frontend uses **React 18** with TypeScript, **Vite** for building, and **Wouter** for routing. **TanStack Query v5** manages server state. The UI is built with **shadcn/ui** (based on Radix UI primitives) and styled using **Tailwind CSS**. Custom Radiant Components implement a Fluent Design-inspired interface with glass-morphism panels, BentoCard layouts, and gradient backgrounds. The design emphasizes information density, visual hierarchy through gradients, and a premium aesthetic with functional efficiency, using the Inter font family and responsive breakpoints.

### Backend Architecture
The application integrates with the **Moio Platform**, a Django-based AI-enhanced CRM backend, accessible via a public API (`https://api.moio.ai/api/v1`). The API is structured into six core modules: Platform Experience, Core Services, Contacts & Deals, Communications, Campaigns, and Flows & Automation. Authentication uses JWT Bearer tokens with 15-minute access token expiry and rotating refresh tokens, managed by an **AuthContext** on the client side. An **Express.js** server with TypeScript handles local development, featuring custom middleware and a modular route registration pattern. The data layer uses **Drizzle ORM** with PostgreSQL and a schema-first design, supporting an in-memory storage adapter for development.

**API Endpoint Patterns**: CRM module endpoints: `/api/v1/crm/contacts/` (contacts), `/api/v1/crm/deals/` (deals), `/api/v1/crm/tickets/` (tickets), `/api/v1/crm/communications/conversations/` (communications), `/api/v1/crm/knowledge/` (knowledge base and service templates with `?type=service-template`). Note the `/crm/` prefix with slash separator.

**Summary Endpoints**: 
- `/api/v1/crm/communications/summary/` - Returns: total, active, closed, pending counts; awaiting_response (active sessions where latest message is from USER); total_unread; latest_interaction; by_channel breakdown
- `/api/v1/crm/contacts/summary/` - Returns: total, with_email, with_phone, do_not_contact, bounced counts; latest_updated; by_type breakdown
- `/api/v1/crm/dashboard/summary/` - General dashboard metrics

The Campaign module uses a nested structure: `/api/v1/campaigns/campaigns/` for campaign CRUD operations (not `/api/v1/campaigns/`), `/api/v1/campaigns/audiences/` for audience management, and `/api/v1/campaigns/campaigns/dashboard/` for analytics. Campaign list endpoint returns `Campaign[]` directly (not paginated). Campaign fields use: `sent`, `opened`, `responded` (read-only metrics), `created`, `updated` (timestamps), `audience_name`, `audience_size` (derived fields), and `kind` enum (express, one_shot, drip, planned).

**Pagination**: The Django REST Framework backend uses `page` and `page_size` parameters (NOT `offset` and `limit`). Example: `/api/v1/crm/tickets/?page=1&page_size=20`. Trailing slash must be BEFORE query params. Response includes `pagination` object with `total_items`, `current_page`, `total_pages`.

**Ticket API**: PATCH format for `/api/v1/crmtickets/{id}/`: `{assigned, status, priority, description, service, type}`. Status values: `open`, `in_progress`, `resolved`, `closed`. Priority values: `low`, `medium`, `high`, `urgent`. The `assigned` field accepts a contact ID or user ID for assignment.

**Campaign Data Integration**: Express campaigns integrate with Django backend for WhatsApp templates and Excel data import. WhatsApp templates are fetched from Meta's official API via `WhatsappBusinessClient` using credentials from `tenant_configuration`. Excel uploads use multipart/form-data POST to `/campaigns/data/import`, which uses pandas to parse files and create `CampaignDataStaging` records. The frontend stores the staging ID and preview data for field mapping validation before campaign creation.

**Flow Builder Integration**: The Flow Builder uses ReactFlow for visual workflow automation. Node definitions and palette data are fetched from `/flows/definitions/` endpoint. The backend returns `node_definitions` (mapping of node kinds to specs including ports, icons, schemas, and hints) and `palette` (category-grouped available nodes). The React frontend transforms this data to render a dynamic node palette with proper port configurations. Current implementation fetches definitions globally and passes them to the NodePalette component, which falls back to hardcoded data if backend specs are unavailable. Flow data is saved/loaded via `/flows/` and `/flows/{id}/` endpoints with proper trailing slashes for Django compatibility.

**Node Hints System**: Logic nodes now support hints from the API `/api/v1/flows/definitions/` including:
- `description`: Rich node description (overrides default description)
- `example_config`: Sample configuration for the node
- `use_cases`: Common use case examples
- `expression_examples`: Expression/condition examples with descriptions (for conditional nodes)
- `tips`: Configuration guidance and best practices

Icon mapping supports all common Lucide icon names (Hand, GitBranch, Filter, Clock, Link2, Webhook, etc.) with fallback to HelpCircle for unknown icons.

**Preview Armed State & Live Badge**: Flow preview includes automatic arm/disarm lifecycle management:
- Preview automatically arms when "Run Preview" button clicked (visual feedback: "Armed & Live" animated badge)
- Preview automatically disarms when preview drawer closes
- Page unload triggers cleanup via beforeunload event (backend implements timeout-based auto-disarm safety net)
- Live badge animates with pulsing effect to indicate active armed state
- Backend endpoints: `/flows/{flowId}/versions/{versionId}/arm/` and `/disarm/` for explicit control
- API methods in FlowBuilderApiClient: `arm(versionId)` and `disarm(versionId)` for explicit arm/disarm

### Application Structure
The project is organized as a monorepo with `/client` (React frontend), `/server` (Express backend), and `/shared` (common types and schemas). Key architectural decisions include: full-stack type safety using TypeScript, component composition with Radix UI and Tailwind, a glass-morphism UI aesthetic, an API-first backend, and static asset handling via Vite/Express.

### Page Architecture
Core pages include: a landing page, `/dashboard` (featuring KPI metrics and an integrated Command Center for natural language interaction), `/contacts`, `/deals` (Kanban pipeline), `/communications` (WhatsApp chat), `/campaigns`, `/tickets`, `/workflows`, and `/settings`. Shared UI patterns ensure consistency, including a `PageLayout` for consistent page structure, `PageHeader`, `GlassPanel`, and the `CommandCenter` chat interface.

**Automation Studio Tabs**: The `/workflows` page features a multi-tab interface for managing automation components:
- **Flows**: Visual workflow builder with ReactFlow-based canvas for designing automation sequences
- **Scripts**: Python script library for reusable automation logic with approval workflow
- **AI Agents**: Configuration interface for intelligent agents and their tools (agents handle conversations/tasks, tools provide capabilities like API calls)
- **Components**: Management of non-intelligent configurable objects including webhooks (HTTP endpoints), signals (event triggers), internal models (data structures), MCP connections (external service connectors), and JSON schemas (structured output definitions)
- **Analysis**: Dashboard showing automation performance metrics, execution timeline, and health scorecard

**AI Agent Builder**: The agent configuration supports OpenAI Agents SDK patterns:
- **Hosted Tools**: Built-in OpenAI tools (web_search, file_search, computer)
- **Moio Agent Tools**: Platform-specific tools fetched from `/resources/agent_tools/` (filtered by `type !== "builtin"`)
- **MCP Connections**: External service connectors (Outlook, PayPal, etc.) managed in Components section and referenced by agents via multi-select
- **JSON Schemas**: Reusable output schemas for structured responses, managed in Components section and selected for agent output_type
- **Reasoning Models**: o1, o1-mini, o1-preview, o3, o3-mini, o4-mini, gpt-5 support with reasoning_effort (low/medium/high)
- **Handoffs**: Agent-to-agent delegation with handoff_description
- **Tool Configuration**: Tool use behavior (run_llm_again, stop_on_first_tool)

**MCP Connections Manager** (`/workflows/mcp-connections`): CRUD for external service connectors with:
- Connection type: OpenAI Hosted Connector (connector_id) or Custom Server URL
- Server label, authorization token, allowed tools selection
- Require approval settings (always, never, on_first_use)
- Common connectors: Outlook, Gmail, Slack, Notion, GitHub

**JSON Schemas Manager** (`/workflows/json-schemas`): CRUD for output schemas with:
- Visual builder mode for field management (name, type, description, required)
- JSON editor mode for direct schema editing
- Templates for quick start (Simple Response, Contact Info, Task Result)
- Schema versioning and usage tracking

## External Dependencies

### UI & Styling
- **@radix-ui/react-***: Headless UI primitives for accessibility.
- **tailwindcss**: Utility-first CSS framework.
- **class-variance-authority**, **clsx**, **tailwind-merge**: For type-safe and conditional styling.
- **lucide-react**, **react-icons**: Icon libraries.
- **framer-motion**: Animation library.
- **embla-carousel-react**: Carousel component.

### Data & Forms
- **@tanstack/react-query v5**: Server state management.
- **react-hook-form**, **@hookform/resolvers**, **zod**: Form management and validation.
- **date-fns**: Date utilities.
- **react-day-picker**: Calendar component.

### Database & Backend
- **@neondatabase/serverless**: Neon Postgres driver.
- **drizzle-orm**, **drizzle-zod**, **drizzle-kit**: ORM, schema generation, and migration tools.
- **connect-pg-simple**: PostgreSQL session store for Express.

### Routing & State
- **wouter**: Minimalist React router.
- **express**: Node.js web framework.
- **nanoid**: Unique ID generation.

### Development Tools
- **vite**: Build tool.
- **tsx**: TypeScript execution for Node.js.
- **esbuild**: JavaScript bundler.

### Third-Party Integration Readiness
The platform is designed for integration with:
- **WhatsApp Business** (currently connected).
- Integrations include: Gmail, Slack, WordPress, OpenAI, Google Maps, Telegram, and Instagram.

## Settings & Configuration

### Integrations Management
The Settings page (`/settings`) provides full integration management via `/api/v1/settings/integrations/`. Features include:
- Grid display of available integrations with connection status badges
- Configuration modal with tabbed interface (Configuration, Status tabs)
- Per-integration config schemas with field types (text, password, url, boolean)
- Save, Test Connection, and Disconnect operations
- Password visibility toggle for sensitive fields

### Master Data Management
The CRM Master Data tab provides management of reusable data:
- **Knowledge Base**: Articles, FAQs, documentation via `/api/v1/content/knowledge/` (excludes type="service-template")
- **Services**: Service templates with Google Maps integration for service areas
- **Tags**: CRUD via `/api/v1/crmtags/` with color picker and usage counts
- **Contact Types**: CRUD via `/api/v1/crmcontact_types/` with color-coded categories