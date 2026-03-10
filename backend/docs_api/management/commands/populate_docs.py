"""
Management command to populate documentation from existing markdown files.

Usage:
    python manage.py populate_docs           # Import all docs
    python manage.py populate_docs --clean   # Clear and reimport
    python manage.py populate_docs --app crm # Import specific app only
"""
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from docs_api.models import GuideCategory, Guide, CodeExample


class Command(BaseCommand):
    help = "Populate documentation from existing markdown files in docs/apps/"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Clear existing docs before importing",
        )
        parser.add_argument(
            "--app",
            type=str,
            help="Import only a specific app (e.g., crm, flows)",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Automatically publish imported guides",
        )

    def handle(self, *args, **options):
        if options["clean"]:
            self.stdout.write("Clearing existing documentation...")
            Guide.objects.all().delete()
            GuideCategory.objects.all().delete()
            CodeExample.objects.all().delete()

        # Find docs directory
        base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        docs_dir = base_dir / "docs" / "apps"

        if not docs_dir.exists():
            self.stdout.write(self.style.ERROR(f"Docs directory not found: {docs_dir}"))
            return

        # Create main categories
        categories = self._create_categories()

        # Process each app
        app_filter = options.get("app")
        publish = options.get("publish", False)

        for app_dir in sorted(docs_dir.iterdir()):
            if not app_dir.is_dir():
                continue

            app_name = app_dir.name

            if app_filter and app_name != app_filter:
                continue

            self.stdout.write(f"Processing {app_name}...")
            self._process_app(app_dir, app_name, categories, publish)

        # Create getting started guides
        self._create_getting_started(categories, publish)

        self.stdout.write(self.style.SUCCESS("Documentation populated successfully!"))
        self._print_summary()

    def _create_categories(self):
        """Create the main guide categories."""
        categories_data = [
            ("getting-started", "Getting Started", "rocket", 1),
            ("crm", "CRM", "users", 10),
            ("campaigns", "Campaigns", "megaphone", 20),
            ("flows", "Flows & Automation", "git-branch", 30),
            ("chatbot", "Chatbot & AI", "message-circle", 40),
            ("datalab", "DataLab", "database", 50),
            ("integrations", "Integrations", "plug", 60),
            ("api-reference", "API Reference", "code", 100),
        ]

        categories = {}
        for slug, name, icon, order in categories_data:
            category, created = GuideCategory.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "icon": icon, "order": order}
            )
            categories[slug] = category
            if created:
                self.stdout.write(f"  Created category: {name}")

        return categories

    def _process_app(self, app_dir, app_name, categories, publish):
        """Process markdown files from an app directory."""
        # Map apps to categories
        app_category_map = {
            "crm": "crm",
            "campaigns": "campaigns",
            "flows": "flows",
            "chatbot": "chatbot",
            "datalab": "datalab",
            "central_hub": "integrations",
            "recruiter": "crm",
            "assessments": "crm",
            "fluidcms": "integrations",
            "fluidcommerce": "integrations",
            "fam": "integrations",
            "moio_calendar": "integrations",
            "security": "api-reference",
            "websockets_app": "api-reference",
        }

        category_slug = app_category_map.get(app_name, "api-reference")
        category = categories.get(category_slug)

        if not category:
            return

        # Process markdown files
        md_files = [
            ("README.md", f"{app_name.replace('_', ' ').title()} Overview", 1),
            ("interfaces.md", f"{app_name.replace('_', ' ').title()} API Interfaces", 2),
            ("lifecycle.md", f"{app_name.replace('_', ' ').title()} Lifecycle", 3),
            ("data.md", f"{app_name.replace('_', ' ').title()} Data Model", 4),
            ("invariants.md", f"{app_name.replace('_', ' ').title()} Rules & Constraints", 5),
            ("failures.md", f"{app_name.replace('_', ' ').title()} Error Handling", 6),
        ]

        for filename, title, order in md_files:
            file_path = app_dir / filename
            if not file_path.exists():
                continue

            content = file_path.read_text()

            # Skip empty or minimal files
            if len(content.strip()) < 50:
                continue

            slug = f"{app_name}-{filename.replace('.md', '')}"

            # Extract summary from first paragraph
            lines = content.strip().split("\n")
            summary = ""
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    summary = line.strip()[:200]
                    break

            guide, created = Guide.objects.update_or_create(
                slug=slug,
                defaults={
                    "category": category,
                    "title": title,
                    "summary": summary,
                    "content": content,
                    "order": order,
                    "is_published": publish,
                }
            )

            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {title}")

    def _create_getting_started(self, categories, publish):
        """Create getting started guides."""
        category = categories.get("getting-started")
        if not category:
            return

        guides_data = [
            {
                "slug": "quickstart",
                "title": "Quickstart",
                "order": 1,
                "summary": "Get up and running with the Moio Platform API in 5 minutes.",
                "content": """# Quickstart

Get up and running with the Moio Platform API in 5 minutes.

## Prerequisites

- A Moio Platform account
- Your API credentials (email + password)

## Step 1: Get an Access Token

```bash
curl -X POST https://your-domain.com/api/v1/auth/login/ \\
  -H "Content-Type: application/json" \\
  -d '{"email": "your@email.com", "password": "your-password"}'
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

## Step 2: Make Your First API Call

Use the access token to call any API endpoint:

```bash
curl https://your-domain.com/api/v1/crm/contacts/ \\
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Step 3: Explore the API

- Browse the [API Reference](/docs/api-reference) for all endpoints
- Check out [Guides](/docs/guides) for common use cases
- Use the interactive [Swagger UI](/api/swagger/) to test endpoints

## Next Steps

- [Create your first contact](/docs/crm-readme)
- [Set up a campaign](/docs/campaigns-readme)
- [Build a workflow](/docs/flows-readme)
""",
            },
            {
                "slug": "authentication",
                "title": "Authentication",
                "order": 2,
                "summary": "Learn how to authenticate with the Moio Platform API.",
                "content": """# Authentication

All API requests require authentication using JWT (JSON Web Tokens).

## Getting Tokens

### Login

```bash
POST /api/v1/auth/login/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your-password"
}
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

## Using Tokens

Include the access token in the `Authorization` header:

```bash
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

## Token Refresh

Access tokens expire after 5 minutes. Use the refresh token to get a new access token:

```bash
POST /api/v1/auth/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

## Error Responses

| Status | Description |
|--------|-------------|
| 401 | Invalid or expired token |
| 403 | Valid token but insufficient permissions |

## Best Practices

1. **Store tokens securely** - Never expose tokens in URLs or logs
2. **Refresh proactively** - Refresh before expiration to avoid interruptions
3. **Use HTTPS** - Always use HTTPS in production
""",
            },
            {
                "slug": "errors",
                "title": "Error Handling",
                "order": 3,
                "summary": "Understanding API error responses and how to handle them.",
                "content": """# Error Handling

The API uses standard HTTP status codes and returns consistent error responses.

## Error Response Format

```json
{
  "error": "error_code",
  "message": "Human readable message",
  "details": {
    "field_name": ["Specific error for this field"]
  }
}
```

## Common Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Invalid input, validation errors |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | Valid token but no permission |
| 404 | Not Found | Resource doesn't exist |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Internal error (contact support) |

## Validation Errors (400)

```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "details": {
    "email": ["Enter a valid email address."],
    "phone": ["This field is required."]
  }
}
```

## Rate Limiting (429)

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "details": {
    "retry_after": 60
  }
}
```

## Handling Errors

```python
import requests

response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
elif response.status_code == 401:
    # Refresh token and retry
    refresh_token()
    retry_request()
elif response.status_code == 429:
    # Wait and retry
    retry_after = response.json().get("details", {}).get("retry_after", 60)
    time.sleep(retry_after)
    retry_request()
else:
    error = response.json()
    print(f"Error: {error['message']}")
```
""",
            },
        ]

        for guide_data in guides_data:
            guide, created = Guide.objects.update_or_create(
                slug=guide_data["slug"],
                defaults={
                    "category": category,
                    "title": guide_data["title"],
                    "summary": guide_data["summary"],
                    "content": guide_data["content"],
                    "order": guide_data["order"],
                    "is_published": publish,
                }
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {guide_data['title']}")

    def _print_summary(self):
        """Print summary of imported content."""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("Summary:")
        self.stdout.write(f"  Categories: {GuideCategory.objects.count()}")
        self.stdout.write(f"  Guides: {Guide.objects.count()}")
        self.stdout.write(f"  Published: {Guide.objects.filter(is_published=True).count()}")
        self.stdout.write(f"  Code Examples: {CodeExample.objects.count()}")
        self.stdout.write("=" * 50)
