"""
Write shopify.app.toml with client_id and application_url from PlatformConfiguration.

Use this so the toml always reflects platform config (no manual copy). Run before
`shopify app deploy` when deploying the theme app extension.

Usage:
  cd backend && python manage.py shopify_write_app_toml
  cd .. && shopify app deploy

Or from repo root (if manage.py is run from backend):
  python backend/manage.py shopify_write_app_toml --path shopify.app.toml
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from central_hub.models import PlatformConfiguration


def _escape_toml_string(s: str) -> str:
    """Escape for TOML double-quoted string (backslash and quotes)."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


class Command(BaseCommand):
    help = "Write shopify.app.toml with client_id and application_url from PlatformConfiguration."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="Path to shopify.app.toml (default: repo root / shopify.app.toml).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be written without writing.",
        )

    def handle(self, *args, **options) -> None:
        cfg = PlatformConfiguration.objects.first()
        if not cfg:
            self.stderr.write(self.style.ERROR("PlatformConfiguration not found. Create one in Platform Admin."))
            return

        client_id = (cfg.shopify_client_id or "").strip()
        application_url = (cfg.my_url or "").strip().rstrip("/")

        if not client_id:
            self.stderr.write(
                self.style.WARNING("PlatformConfiguration.shopify_client_id is empty. Set it in Platform Admin.")
            )
        if not application_url:
            self.stderr.write(
                self.style.WARNING("PlatformConfiguration.my_url is empty or not set. Set it in Platform Admin.")
            )

        path = options.get("path")
        if path:
            toml_path = Path(path).resolve()
        else:
            # Repo root: parent of backend (where BASE_DIR points when running from backend)
            repo_root = Path(settings.BASE_DIR).parent
            toml_path = repo_root / "shopify.app.toml"

        if not toml_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {toml_path}"))
            return

        content = toml_path.read_text(encoding="utf-8")

        # Replace client_id and application_url lines (preserve trailing comment/newline)
        def replace_key(key: str, value: str) -> None:
            nonlocal content
            pattern = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*)[^\n]*(\n)', re.MULTILINE)
            escaped = _escape_toml_string(value)
            def repl(m):
                return m.group(1) + '"' + escaped + '"' + m.group(2)
            content = pattern.sub(repl, content, count=1)

        replace_key("client_id", client_id)
        replace_key("application_url", application_url)
        # App proxy URL: storefront /apps/moio-chat/... forwards to this backend path
        if application_url:
            proxy_url = application_url.rstrip("/") + "/api/v1/integrations/shopify/app-proxy"
            replace_key("url", proxy_url)

        if options.get("dry_run"):
            self.stdout.write(content)
            self.stdout.write(self.style.SUCCESS(f"[dry-run] Would write {toml_path}"))
            return

        toml_path.write_text(content, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Updated {toml_path} with client_id and application_url from PlatformConfiguration."))
        self.stdout.write("Run from repo root: shopify app deploy")
