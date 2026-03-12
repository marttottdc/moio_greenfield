from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


VENDOR_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

DEFAULT_CAPABILITIES: dict[str, bool] = {
    "supportsThinking": True,
    "supportsVerbosity": True,
    "supportsTemperature": True,
    "supportsMaxOutputTokens": True,
    "supportsTools": True,
    "supportsStreaming": True,
}


class VendorStore:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._vendors: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._vendors = []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._vendors = []
            return
        vendors = payload.get("vendors") if isinstance(payload, dict) else None
        if not isinstance(vendors, list):
            self._vendors = []
            return
        normalized: list[dict[str, Any]] = []
        for entry in vendors:
            if not isinstance(entry, dict):
                continue
            try:
                normalized.append(self._normalize_entry(entry))
            except ValueError:
                continue
        self._vendors = normalized

    def _save(self) -> None:
        payload = {"vendors": self._vendors}
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _mask_api_key(value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        if len(text) <= 8:
            return "*" * len(text)
        return f"{text[:4]}...{text[-4:]}"

    @staticmethod
    def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
        vendor_id = str(raw.get("id", "")).strip().lower()
        if not vendor_id or not VENDOR_ID_RE.match(vendor_id):
            raise ValueError("vendor id must match ^[a-zA-Z0-9_-]+$")

        label = str(raw.get("label", vendor_id)).strip() or vendor_id
        base_url = str(raw.get("base_url", "")).strip()
        models_endpoint = str(raw.get("models_endpoint", "/models")).strip() or "/models"
        if not models_endpoint.startswith("/"):
            models_endpoint = "/" + models_endpoint

        api_key = str(raw.get("api_key", "")).strip()
        api_key_env = str(raw.get("api_key_env", "")).strip()
        enabled = bool(raw.get("enabled", True))
        source = str(raw.get("source", "custom")).strip() or "custom"
        reason = str(raw.get("reason", "")).strip()

        models_raw = raw.get("models")
        models: list[dict[str, str]] = []
        if isinstance(models_raw, list):
            for item in models_raw:
                if not isinstance(item, dict):
                    continue
                model_id = str(item.get("id", "")).strip()
                if not model_id:
                    continue
                model_label = str(item.get("label", model_id)).strip() or model_id
                models.append({"id": model_id, "label": model_label})

        caps_raw = raw.get("capabilities")
        capabilities = dict(DEFAULT_CAPABILITIES)
        if isinstance(caps_raw, dict):
            for key in DEFAULT_CAPABILITIES:
                if key in caps_raw:
                    capabilities[key] = bool(caps_raw[key])

        return {
            "id": vendor_id,
            "label": label,
            "base_url": base_url,
            "models_endpoint": models_endpoint,
            "api_key": api_key,
            "api_key_env": api_key_env,
            "enabled": enabled,
            "source": source,
            "reason": reason,
            "models": models,
            "capabilities": capabilities,
        }

    def seed_defaults(self, vendors: list[dict[str, Any]]) -> None:
        changed = False
        for raw in vendors:
            if not isinstance(raw, dict):
                continue
            entry = self._normalize_entry(raw)
            existing = self.get(entry["id"], include_secret=True)
            if existing is None:
                self._vendors.append(entry)
                changed = True
                continue
            merged = dict(existing)
            # Keep user-managed fields, but refresh default metadata and model presets.
            merged["label"] = entry["label"]
            if not merged.get("base_url"):
                merged["base_url"] = entry["base_url"]
            if not merged.get("models_endpoint"):
                merged["models_endpoint"] = entry["models_endpoint"]
            if not merged.get("api_key_env"):
                merged["api_key_env"] = entry["api_key_env"]
            merged["source"] = entry["source"]
            merged["capabilities"] = entry["capabilities"]
            if not merged.get("models"):
                merged["models"] = entry["models"]
            if merged != existing:
                self._replace(entry["id"], merged)
                changed = True
        if changed:
            self._save()

    def _replace(self, vendor_id: str, replacement: dict[str, Any]) -> None:
        normalized = self._normalize_entry(replacement)
        for idx, item in enumerate(self._vendors):
            if item.get("id") == vendor_id:
                self._vendors[idx] = normalized
                return
        self._vendors.append(normalized)

    def list(self, *, include_secret: bool = False) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in sorted(self._vendors, key=lambda entry: str(entry.get("id", ""))):
            entry = dict(item)
            api_key = str(entry.get("api_key", "")).strip()
            if include_secret:
                entry["has_api_key"] = bool(api_key)
            else:
                entry.pop("api_key", None)
                entry["has_api_key"] = bool(api_key)
                entry["api_key_masked"] = self._mask_api_key(api_key)
            entries.append(entry)
        return entries

    def get(self, vendor_id: str, *, include_secret: bool = False) -> dict[str, Any] | None:
        key = vendor_id.strip().lower()
        for item in self._vendors:
            if item.get("id") != key:
                continue
            entry = dict(item)
            api_key = str(entry.get("api_key", "")).strip()
            if include_secret:
                entry["has_api_key"] = bool(api_key)
            else:
                entry.pop("api_key", None)
                entry["has_api_key"] = bool(api_key)
                entry["api_key_masked"] = self._mask_api_key(api_key)
            return entry
        return None

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("vendor payload must be an object")

        raw_id = str(payload.get("id", "")).strip().lower()
        existing = self.get(raw_id, include_secret=True) if raw_id else None

        merged: dict[str, Any] = {}
        if existing is not None:
            merged.update(existing)
        merged.update(payload)

        if existing is not None:
            if "api_key" not in payload:
                merged["api_key"] = str(existing.get("api_key", "")).strip()
            if "models" not in payload:
                merged["models"] = existing.get("models", [])
            if "capabilities" not in payload:
                merged["capabilities"] = existing.get("capabilities", dict(DEFAULT_CAPABILITIES))
            if "source" not in payload:
                merged["source"] = existing.get("source", "custom")
            if "reason" not in payload:
                merged["reason"] = existing.get("reason", "")

        entry = self._normalize_entry(merged)
        self._replace(entry["id"], entry)
        self._save()
        return self.get(entry["id"], include_secret=False) or {}

    def delete(self, vendor_id: str) -> bool:
        key = vendor_id.strip().lower()
        before = len(self._vendors)
        self._vendors = [item for item in self._vendors if item.get("id") != key]
        changed = len(self._vendors) != before
        if changed:
            self._save()
        return changed

    def resolve_api_key(self, vendor_id: str) -> str | None:
        entry = self.get(vendor_id, include_secret=True)
        if not entry:
            return None
        api_key = str(entry.get("api_key", "")).strip()
        if api_key:
            return api_key
        api_key_env = str(entry.get("api_key_env", "")).strip()
        if api_key_env:
            return os.getenv(api_key_env)
        return None

    def list_models_from_endpoint(self, vendor_id: str, timeout_seconds: float = 20.0) -> dict[str, Any]:
        entry = self.get(vendor_id, include_secret=True)
        if not entry:
            raise ValueError(f"vendor not found: {vendor_id}")
        if not bool(entry.get("enabled", True)):
            raise ValueError(f"vendor {vendor_id} is disabled")

        base_url = str(entry.get("base_url", "")).strip()
        if not base_url:
            raise ValueError(f"vendor {vendor_id} has no base_url configured")
        models_endpoint = str(entry.get("models_endpoint", "/models")).strip() or "/models"
        if not models_endpoint.startswith("/"):
            models_endpoint = "/" + models_endpoint
        url = urlparse.urljoin(base_url.rstrip("/") + "/", models_endpoint.lstrip("/"))

        headers = {"Accept": "application/json"}
        api_key = self.resolve_api_key(vendor_id)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urlrequest.Request(url, headers=headers, method="GET")
        try:
            with urlrequest.urlopen(req, timeout=max(1.0, float(timeout_seconds))) as resp:
                raw_text = resp.read().decode("utf-8", errors="replace")
                status_code = int(resp.getcode() or 0)
        except urlerror.HTTPError as exc:
            raise ValueError(f"models endpoint returned HTTP {exc.code}") from exc
        except urlerror.URLError as exc:
            raise ValueError(f"models endpoint request failed: {exc.reason}") from exc

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError("models endpoint did not return valid JSON") from exc

        models = self._extract_models(payload)
        updated = self.get(vendor_id, include_secret=True)
        if updated is not None:
            updated["models"] = models
            self._replace(vendor_id.strip().lower(), updated)
            self._save()

        return {
            "vendorId": vendor_id.strip().lower(),
            "url": url,
            "statusCode": status_code,
            "count": len(models),
            "models": models,
        }

    @staticmethod
    def _extract_models(payload: Any) -> list[dict[str, str]]:
        candidates: list[Any] = []
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict):
            for key in ("data", "models", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    candidates = value
                    break
            if not candidates:
                maybe_models = payload.get("model_list")
                if isinstance(maybe_models, list):
                    candidates = maybe_models

        dedup: dict[str, dict[str, str]] = {}
        for item in candidates:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
            if not model_id:
                continue
            label = str(item.get("label") or item.get("name") or model_id).strip() or model_id
            dedup[model_id] = {"id": model_id, "label": label}

        return [dedup[key] for key in sorted(dedup.keys())]
