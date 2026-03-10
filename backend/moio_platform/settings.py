"""
Django settings for moio_platform project.
"""

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from corsheaders.defaults import default_headers
import dj_database_url

from decouple import config
from dotenv import load_dotenv
from moio_platform.lib.tools import get_config_value
import subprocess
from logtail import LogtailHandler

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# Build paths inside the project like this: BASE_DIR / 'subdir'.
APPS_DIR = BASE_DIR / 'central_hub'


def _env_bool(key, default=False):
    value = get_config_value(key)
    if value is None:
        return default
    return str(value).lower() in ['true', '1', 't', 'y', 'yes']


def _build_database_url_from_parts():
    host = get_config_value('DB_HOST')
    name = get_config_value('DB_NAME')
    user = get_config_value('DB_USER')
    password = get_config_value('DB_PASSWORD')
    port = get_config_value('DB_PORT', '5432')

    if not all([host, name, user]):
        return None

    encoded_password = quote_plus(password or '')
    return f'postgresql://{quote_plus(user)}:{encoded_password}@{host}:{port}/{name}'


DATABASE_URL = get_config_value('DATABASE_URL') or _build_database_url_from_parts()
USE_LOCAL_DEV_DEFAULTS = _env_bool('USE_LOCAL_DEV_DEFAULTS', default=not DATABASE_URL)
DJANGO_TENANTS_ENABLED = _env_bool('DJANGO_TENANTS_ENABLED', default=False)
PUBLIC_SCHEMA_NAME = str(get_config_value('PUBLIC_SCHEMA_NAME', 'public') or 'public').strip() or 'public'
TENANT_MODEL = "tenancy.Tenant"
TENANT_DOMAIN_MODEL = "tenancy.TenantDomain"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# config('SECRET_KEY')
SECRET_KEY = get_config_value('SECRET_KEY', "iugfr6yuih78g7tg7g7asesa")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_config_value('DEBUG', 'false')
DEBUG = DEBUG.lower() in ['true', '1', 't', 'y', 'yes']

if DEBUG:
    print(f" ---- WARNING RUNNING IN DEBUG MODE ----")
else:
    print(" ---- PRODUCTION MODE ----")

ALLOWED_HOSTS = [".moio.ai", "127.0.0.1", "localhost", "*"]

# Application definition

SHARED_APPS = [
    "django_tenants",
    "corsheaders",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "channels",
    "django_extensions",
    "cacheops",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "storages",
    "viewflow",
    "django_celery_results",
    "django_celery_beat",
    "mcp_server",
    "tenancy",
    "central_hub",
    "security",
    "docs_api.apps.DocsApiConfig",
]

TENANT_APPS = [
    "notifications",
    "assessments",
    "campaigns",
    "chatbot.apps.ChatbotConfig",
    "crm",
    "flows",
    "moio_calendar",
    "websockets_app",
    "datalab.apps.DatalabConfig",
]

API_ONLY_APPS = [
    "corsheaders",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "channels",
    "django_extensions",
    "cacheops",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "storages",
    "viewflow",
    "django_celery_results",
    "django_celery_beat",
    "mcp_server",
    "tenancy",
    "central_hub",
    "security",
    "docs_api.apps.DocsApiConfig",
    *TENANT_APPS,
]

INSTALLED_APPS = (
    SHARED_APPS + [app for app in TENANT_APPS if app not in SHARED_APPS]
    if DJANGO_TENANTS_ENABLED
    else API_ONLY_APPS
)

MIDDLEWARE = [
    *(
        [
            "tenancy.host_rewrite.HostRewriteFromJWTMiddleware",
            "django_tenants.middleware.main.TenantMainMiddleware",
        ]
        if DJANGO_TENANTS_ENABLED
        else []
    ),
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'tenancy.middleware.TenantMiddleware',
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "tenancy.authentication.UserApiKeyAuthentication",
        "tenancy.authentication.TenantJWTAAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "security.authentication.ServiceJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "moio_platform.api_exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":
    timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME":
    timedelta(days=7),
    "ROTATE_REFRESH_TOKENS":
    False,
    "BLACKLIST_AFTER_ROTATION":
    True,
    "TOKEN_OBTAIN_SERIALIZER":
    "tenancy.authentication.TenantTokenObtainPairSerializer",
}

SERVICE_TOKEN_SECRET = get_config_value('SERVICE_TOKEN_SECRET',
                                        'dev-secret-key-change-in-production')

# DJANGO_MCP_AUTHENTICATION_CLASSES = ['rest_framework.authentication.TokenAuthentication',]

ROOT_URLCONF = 'moio_platform.urls'

CORS_ALLOWED_ORIGINS = [
    "https://landing.moiodigital.com",
    "https://ui.moio.ai",
    "https://407e82de-8e0f-4d55-9571-e93ff4bdb986-00-3mzgqcz01drdq.spock.replit.dev",
]

CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_SAMESITE = 'None'
CSRF_COOKIE_SECURE = True  # For HTTPS
CSRF_TRUSTED_ORIGINS = [
    'https://moio.ngrok.dev', 'https://devcrm.moio.ai', 'https://api.moio.ai',
    'https://platform.moio.ai'
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.replit\.dev$",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-moio-client-version',  # Important: Allow the custom header
]

CSRF_TRUSTED_ORIGINS = [
    "https://407e82de-8e0f-4d55-9571-e93ff4bdb986-00-3mzgqcz01drdq.spock.replit.dev",
    "https://ui.moio.ai"
]

if DEBUG:
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None
    SESSION_COOKIE_SAMESITE = 'None'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'None'
    CSRF_COOKIE_SECURE = True

CORS_URLS_REGEX = r"^/api/.*$"

# Security settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = False

SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.media',
                'central_hub.context_processor.site_configuration',
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_USER_MODEL = "tenancy.MoioUser"

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = get_config_value('EMAIL_HOST', '')
EMAIL_PORT = get_config_value('EMAIL_PORT', 443)
EMAIL_USE_TLS = get_config_value('EMAIL_USE_TLS', True)
EMAIL_HOST_USER = get_config_value('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = get_config_value('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = get_config_value('DEFAULT_FROM_EMAIL', '')

WSGI_APPLICATION = 'moio_platform.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

if DJANGO_TENANTS_ENABLED:
    if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
        raise RuntimeError("DJANGO_TENANTS_ENABLED requires PostgreSQL; SQLite is not supported.")
    DATABASES["default"]["ENGINE"] = "django_tenants.postgresql_backend"
    DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)
    TENANT_MODEL = "tenancy.Tenant"
    TENANT_DOMAIN_MODEL = "tenancy.TenantDomain"
    TENANT_LIMIT_SET_CALLS = True
    SHOW_PUBLIC_IF_NO_TENANT_FOUND = True
    PG_EXTRA_SEARCH_PATHS = []
else:
    DATABASE_ROUTERS = []

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME':
        'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME':
        'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME':
        'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME':
        'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

# LANGUAGE_CODE = 'en-us'
# TIME_ZONE = 'UTC'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Montevideo'

LANGUAGES = [
    ('en', 'English'),
    ('es', 'Español'),
]

USE_I18N = True
USE_TZ = True

LOCALE_PATHS = [
    BASE_DIR / "locale",  # where translations will be stored
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ========= Celery Configurations =======================

REDIS_URL = get_config_value('REDIS_URL')

CELERY_BROKER_URL = REDIS_URL or 'memory://'
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'

CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_SERIALIZER = 'json'

# App name for queue prefixes
APP_NAME = os.environ.get("APP_NAME", "default")

# Named queues
HIGH_PRIORITY_Q = f'{APP_NAME}-HIGH'
MEDIUM_PRIORITY_Q = f'{APP_NAME}-MEDIUM'
LOW_PRIORITY_Q = f'{APP_NAME}-LOW'
FLOWS_Q = f'{APP_NAME}-FLOWS'

# Celery queue configuration
CELERY_QUEUES = {
    'default': {
        'exchange': 'default',
        'routing_key': 'default'
    },
    'flows': {
        'exchange': 'flows',
        'routing_key': 'flows'
    },
}

CELERY_TASK_ROUTES = {
    'flows.tasks.*': {
        'queue': FLOWS_Q
    }
}

ASGI_APPLICATION = "moio_platform.asgi.application"

if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
# ========= AWS S3 Bucket Configurations =======================

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

# AWS credentials
AWS_ACCESS_KEY_ID = get_config_value('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = get_config_value('AWS_SECRET_ACCESS_KEY')
AWS_S3_REGION_NAME = get_config_value('AWS_REGION')
AWS_STORAGE_STATIC_BUCKET_NAME = get_config_value('AWS_STORAGE_STATIC_BUCKET_NAME')
AWS_STORAGE_MEDIA_BUCKET_NAME = get_config_value('AWS_STORAGE_MEDIA_BUCKET_NAME')

USE_S3_STORAGE = all([
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_S3_REGION_NAME,
    AWS_STORAGE_STATIC_BUCKET_NAME,
    AWS_STORAGE_MEDIA_BUCKET_NAME,
])

if USE_S3_STORAGE:
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }

    AWS_S3_STATIC_DOMAIN = f'{AWS_STORAGE_STATIC_BUCKET_NAME}.s3.amazonaws.com'
    STATICFILES_STORAGE = 'moio_platform.storage_backends.StaticStorage'
    AWS_STATIC_LOCATION = f'{get_config_value("APP_NAME", "APP_NAME")}/static/'
    STATIC_URL = f'https://{AWS_S3_STATIC_DOMAIN}/{AWS_STATIC_LOCATION}'

    AWS_S3_MEDIA_DOMAIN = f'{AWS_STORAGE_MEDIA_BUCKET_NAME}.s3.amazonaws.com'
    DEFAULT_FILE_STORAGE = 'moio_platform.storage_backends.MediaStorage'
    AWS_MEDIA_LOCATION = f'{get_config_value("APP_NAME","APP_NAME")}/media/'
    MEDIA_URL = f'https://{AWS_S3_MEDIA_DOMAIN}/{AWS_MEDIA_LOCATION}'
else:
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

#CACHE OPS

CACHEOPS_ENABLED = bool(REDIS_URL) and _env_bool('CACHEOPS_ENABLED', True)
CACHEOPS_REDIS = REDIS_URL
CACHEOPS_DEGRADE_ON_FAILURE = True
CACHEOPS = {
    # Cache all queries for Product for 10 minutes (600 sec)
    'central_hub.*': {
        'ops': 'all',
        'timeout': 6000
    },
    'crm.*': {
        'ops': 'all',
        'timeout': 6000
    },
    'chatbot.*': {
        'ops': 'all',
        'timeout': 3000
    },

    # 'your_app.*': {'ops': {'fetch', 'count', 'aggregate'}, 'timeout': 300},
}

APP_VERSION = os.getenv("IMAGE_TAG", "unknown")
if APP_VERSION == "unknown":
    with open(BASE_DIR / 'version.txt', 'r') as f:
        APP_VERSION = f.read().strip()

print(f"Moio Build: {APP_VERSION}")

LOGTAIL_SOURCE_TOKEN = get_config_value('LOGTAIL_SOURCE_TOKEN')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        #'logtail': {
        #            'class': 'logtail.LogtailHandler',
        #            'source_token': LOGTAIL_SOURCE_TOKEN,
        #            'host': 'https://s1258142.eu-nbg-2.betterstackdata.com',
        #        },
    },
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    "root": {  # Add this
        "handlers": ["console", ], #"logtail"
        "level": "INFO",
    },
    "loggers": {

        "django": {  # Specific logger for Django
            "handlers": ["console", ], #"logtail"
            "level": "INFO",
            "propagate": False,
        },
        "celery": {  # Add this
            "handlers": ["console", ], #"logtail"
            "level": "INFO",  # or "DEBUG" to catch more
            "propagate": False,
        },
    },
}

DJANGO_MCP_GLOBAL_SERVER_CONFIG = {
    "name": "moio_mcp",
    "instructions": "We are a small company with big dreams",
    "stateless": True
}

# allow up to 20 MB of raw request data
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

SPECTACULAR_SETTINGS = {
    # ─────────────────────────────────────────────────────────────────────────
    # Branding & Metadata
    # ─────────────────────────────────────────────────────────────────────────
    "TITLE": "Moio Platform API",
    "DESCRIPTION": """
## AI-powered CRM, Automation & Data Platform

Moio Platform provides a comprehensive API for:

- **CRM** - Contacts, tickets, deals, products, knowledge base
- **Campaigns** - Marketing campaigns with audience targeting
- **Flows** - Visual workflow automation engine
- **Chatbot** - AI conversational agents (WhatsApp, Email, Instagram)
- **DataLab** - Data import, transformation, and analytics

### Authentication

All endpoints require JWT Bearer authentication unless marked as public.

```
Authorization: Bearer <access>
```

Obtain tokens via `POST /api/v1/auth/login/` with email and password.

### Rate Limiting

API requests are rate-limited per tenant. Contact support for limit increases.

### Errors

All errors return a consistent JSON structure:
```json
{
  "error": "error_code",
  "message": "Human readable message",
  "details": {}
}
```
""",
    "VERSION": "1.0.0",
    "CONTACT": {"name": "Moio Support", "url": "https://moio.io", "email": "support@moio.io"},
    "LICENSE": {"name": "Proprietary", "url": "https://moio.io/terms"},
    "SERVE_INCLUDE_SCHEMA": False,

    # ─────────────────────────────────────────────────────────────────────────
    # API Grouping (Tags)
    # ─────────────────────────────────────────────────────────────────────────
    "TAGS": [
        {"name": "Auth", "description": "Authentication, tokens, and user registration"},
        {"name": "CRM - Contacts", "description": "Contact management and search"},
        {"name": "CRM - Tickets", "description": "Support ticket tracking"},
        {"name": "CRM - Deals", "description": "Sales pipeline and deal management"},
        {"name": "CRM - Products", "description": "Product catalog"},
        {"name": "CRM - Knowledge", "description": "Knowledge base articles"},
        {"name": "CRM - Tags", "description": "Tagging system"},
        {"name": "CRM - Activities", "description": "Activity logging"},
        {"name": "Campaigns", "description": "Marketing campaigns and execution"},
        {"name": "Audiences", "description": "Audience targeting and segmentation"},
        {"name": "Flows", "description": "Workflow definitions and versions"},
        {"name": "Flow Execution", "description": "Flow triggers and execution logs"},
        {"name": "Flow Schedules", "description": "Scheduled flow triggers"},
        {"name": "Scripts", "description": "Python script nodes for flows"},
        {"name": "Chatbot", "description": "AI agents and session management"},
        {"name": "DataLab - Files", "description": "File upload and management"},
        {"name": "DataLab - Imports", "description": "Data import and transformation"},
        {"name": "DataLab - ResultSets", "description": "Processed data results"},
        {"name": "DataLab - Datasets", "description": "Versioned dataset management"},
        {"name": "Integrations", "description": "External service integrations"},
        {"name": "Calendar", "description": "Event and booking management"},
        {"name": "Resources", "description": "WhatsApp templates and resources"},
        {"name": "Settings", "description": "Tenant configuration"},
        {"name": "Health", "description": "System health and status"},
    ],

    # ─────────────────────────────────────────────────────────────────────────
    # Security Schemes
    # ─────────────────────────────────────────────────────────────────────────
    "SECURITY": [{"bearerAuth": []}],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT access from /api/v1/auth/login/",
            },
            "serviceToken": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Service-to-service token with scopes",
            },
        }
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Schema Generation
    # ─────────────────────────────────────────────────────────────────────────
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "SCHEMA_PATH_PREFIX_TRIM": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
    "SORT_OPERATIONS": True,
    "SORT_OPERATION_PARAMETERS": True,
    "ENUM_NAME_OVERRIDES": {},
    "POSTPROCESSING_HOOKS": [],

    # ─────────────────────────────────────────────────────────────────────────
    # Swagger UI Settings
    # ─────────────────────────────────────────────────────────────────────────
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "filter": True,
        "docExpansion": "none",
    },
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",

    # ─────────────────────────────────────────────────────────────────────────
    # ReDoc Settings
    # ─────────────────────────────────────────────────────────────────────────
    "REDOC_DIST": "SIDECAR",
}
