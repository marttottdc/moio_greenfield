
# Moio.ai - Intelligent CRM Platform for SMEs

Moio.ai is a comprehensive Customer Relationship Management (CRM) platform designed specifically for small and medium enterprises (SMEs). Built with Django and powered by artificial intelligence, it provides an all-in-one solution for managing customer relationships, communications, and business operations.

## 🚀 Key Features

### 💬 **Unified Communications Hub**
- **Multi-channel Support**: WhatsApp, Instagram, Telegram, Facebook Messenger, Email, and Web Chat
- **Centralized Conversations**: Manage all customer interactions from a single interface
- **Real-time Chat Management**: Live chat sessions with message history and status tracking
- **AI-powered Responses**: Intelligent auto-replies and conversation routing

### 🤖 **AI-Powered Automation**
- **Intelligent Agent Configuration**: Multiple AI agents with custom instructions and behavior
- **GPT Integration**: OpenAI GPT-4o, GPT-4, and GPT-3.5 Turbo support
- **Smart Contact Classification**: Automatic lead scoring and contact categorization
- **Predictive Analytics**: AI-driven insights for sales optimization

### 👥 **Contact & Customer Management**
- **Advanced Contact Database**: Comprehensive customer profiles with interaction history
- **Lead Management**: Track prospects through the sales funnel
- **Customer Segmentation**: Organize contacts by type, source, and behavior
- **Activity Tracking**: Record all customer interactions and touchpoints

### 🎫 **Support & Ticketing System**
- **Incident Management**: Full-featured ticketing system for customer support
- **Ticket Tracking**: Status monitoring and resolution workflows
- **Team Collaboration**: Assign tickets to team members and track progress
- **Knowledge Base**: Integrated documentation and FAQ management

### 📦 **E-commerce Integration**
- **WooCommerce Sync**: Seamless integration with WordPress/WooCommerce stores
- **Shopify Embedded App**: OAuth install, session-token auth, webhooks (GDPR/uninstall), and sync (see [docs/shopify_setup.md](docs/shopify_setup.md))
- **Order Management**: Track orders, shipments, and delivery status
- **Product Catalog**: Comprehensive product database with search capabilities
- **Inventory Management**: Stock tracking and product variant support

### 📊 **Business Intelligence**
- **Dashboard Analytics**: Real-time KPIs and performance metrics
- **Sales Pipeline**: Visual deal tracking and conversion analysis
- **Reporting Tools**: Custom reports and data visualization
- **Performance Insights**: Team productivity and customer satisfaction metrics

### 🔗 **Integrations & Webhooks**
- **Webhook Management**: Custom webhook configurations for external integrations
- **API Access**: RESTful API for third-party integrations
- **Social Media**: Facebook, Instagram, and WhatsApp Business API integration
- **Email Systems**: SMTP configuration and email campaign management

## 🏗️ **Technical Architecture**

### **Backend Stack**
- **Framework**: Django 4.x with Python 3.x
- **Database**: PostgreSQL with full-text search capabilities
- **Task Queue**: Celery for background job processing
- **WebSockets**: Real-time communication with Django Channels
- **API**: RESTful endpoints with Django REST Framework

### **Frontend Technologies**
- **UI Framework**: Bootstrap 5 with responsive design
- **Interactive Components**: HTMX for dynamic content loading
- **Real-time Updates**: WebSocket connections for live data
- **Charts & Analytics**: Interactive dashboard visualizations

### **AI & Machine Learning**
- **OpenAI Integration**: GPT models for intelligent conversations
- **Vector Search**: Embedding-based content search and recommendations
- **Natural Language Processing**: Text analysis and sentiment detection
- **Automated Workflows**: AI-driven task automation

## 🚀 **Getting Started on Replit**

This project is optimized for deployment on Replit. Simply fork the repository and run:

1. **Install Dependencies**: Dependencies are automatically installed from `requirements.txt`
2. **Database Setup**: Run migrations to set up the database schema
3. **Configure Environment**: Set up your OpenAI API keys and other integrations
4. **Launch Application**: The app runs on port 5000 and is accessible via the provided URL

### **Available Commands**
- `python manage.py migrate` - Set up database tables
- `python manage.py collectstatic` - Collect static files
- `python manage.py createsuperuser` - Create admin user
- Run the application using the built-in workflow

## 🔧 **Configuration**

### **Environment Variables**
Configure the following in your Replit Secrets:
- `OPENAI_API_KEY` - OpenAI API access
- `WHATSAPP_ACCESS_TOKEN` - WhatsApp Business API
- `FACEBOOK_APP_ID` - Facebook/Instagram integration
- `SMTP_*` - Email configuration settings

### **Multi-tenant Support**
The platform supports multiple organizations with:
- Tenant isolation for data security
- Custom branding per tenant
- Role-based access control
- Scalable architecture

### **Test Tenant (Development)**
Para tests (API y frontend), usa el tenant de prueba. Ver [backend/docs/TEST_TENANT.md](backend/docs/TEST_TENANT.md).

**Credenciales:** `test@moio.ai` / `test123`  
**Crear tenant:** `./backend/scripts/create_test_tenant.sh` (con backend en http://127.0.0.1:8093)

### **Agent Console (AI Chat)**
The Agent Console (`/agent-console`) provides interactive AI sessions with workspace and model selection. To run it locally:

1. **Backend** (ASGI + WebSockets): `hypercorn -c file:hypercorn_dev.py moio_platform.asgi:application` (port 8093)
2. **Frontend**: `cd frontend && npm run dev` (port 5177; proxies `/api` and `/ws` to backend)
3. **Redis**: Required for Channels; use `REDIS_URL=redis://localhost:6379/0` (or InMemoryChannelLayer if Redis unavailable)
4. **Agent config**: OpenAI API key comes only from **tenant IntegrationConfig** (Settings → Integrations → OpenAI). No env fallback.

Log in via the platform, then open `/agent-console` to chat with the AI agent.

## 📱 **Supported Platforms**

### **Communication Channels**
- WhatsApp Business API
- Facebook Messenger
- Instagram Direct
- Telegram Bot API
- Email (SMTP/IMAP)
- Web Chat Widget

### **E-commerce Platforms**
- WooCommerce
- WordPress
- Custom API integrations
- Webhook-based connections

## 🎯 **Use Cases**

- **Small Businesses**: Complete CRM solution with AI assistance
- **E-commerce Stores**: Order management with multi-channel support
- **Service Companies**: Ticketing system with customer communication
- **Sales Teams**: Pipeline management with lead scoring
- **Customer Support**: Unified inbox with intelligent routing

## 🛡️ **Security Features**

- **Data Encryption**: Secure data transmission and storage
- **Access Control**: Role-based permissions and tenant isolation
- **API Security**: Token-based authentication
- **Compliance**: GDPR-ready data handling

## 📈 **Pricing Plans**

- **Free Trial**: 3 months full access with up to 50 conversations
- **Starter**: $50/month - Up to 1,000 contacts and 200 conversations
- **Professional**: $250/month - Up to 10,000 contacts with advanced features
- **Enterprise**: Custom pricing for large organizations

## 🤝 **Support & Documentation**

- **Live Chat**: Available through WhatsApp integration
- **Email Support**: Tiered support based on plan level
- **Knowledge Base**: Comprehensive documentation and guides
- **Core API Reference**: Authentication (`/api/v1/auth/*`) and Settings (`/api/v1/settings/*`) endpoints match the contracts in [`docs/MOIO_API_CORE.md`](docs/MOIO_API_CORE.md) so frontend clients can plug directly into the Core module
- **Community**: User forums and resource sharing

## 📄 **License**

© 2025 Moio Digital Business Services SAS. All rights reserved.

---

**Built with ❤️ for SMEs who want to grow smart, not just fast.**

For more information, visit [moiodigital.com](https://moiodigital.com) or contact us via WhatsApp.
