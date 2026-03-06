from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import shutil
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SAFE_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_component(raw: str, fallback: str) -> str:
    normalized = _SAFE_COMPONENT_RE.sub("_", (raw or "").strip()).strip("._")
    return normalized or fallback


def resolve_workspace_media_root(workspace_root: Path, tenant_schema: str, workspace_slug: str) -> Path:
    base = Path(os.getenv("REPLICA_MEDIA_ROOT", "")).expanduser()
    if not str(base).strip():
        base = workspace_root / ".data" / "media"
    tenant = _safe_component(tenant_schema, "public")
    workspace = _safe_component(workspace_slug, "main")
    return (base / tenant / workspace).resolve()


@dataclass(slots=True)
class MediaLocation:
    local_path: Path
    relative_path: str
    local_url: str
    download_url: str
    s3_key: str
    s3_url: str
    mime_type: str
    size_bytes: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "localPath": str(self.local_path),
            "relativePath": self.relative_path,
            "localUrl": self.local_url,
            "downloadUrl": self.download_url,
            "s3Key": self.s3_key,
            "s3Url": self.s3_url,
            "mimeType": self.mime_type,
            "sizeBytes": self.size_bytes,
        }


class MediaStore:
    def __init__(
        self,
        *,
        workspace_root: Path,
        tenant_schema: str,
        workspace_slug: str,
        logger: Any | None = None,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.tenant_schema = _safe_component(tenant_schema, "public")
        self.workspace_slug = _safe_component(workspace_slug, "main")
        self.log = logger
        self.local_root = resolve_workspace_media_root(self.workspace_root, tenant_schema, workspace_slug)
        self.local_root.mkdir(parents=True, exist_ok=True)

        self.url_prefix = (os.getenv("REPLICA_MEDIA_URL_PREFIX", "/media") or "/media").strip()
        if not self.url_prefix.startswith("/"):
            self.url_prefix = "/" + self.url_prefix

        self.backend = (os.getenv("REPLICA_MEDIA_BACKEND", "local") or "local").strip().lower()
        self._s3_client: Any | None = None
        self.s3_bucket = (os.getenv("REPLICA_S3_BUCKET", "") or "").strip()
        self.s3_region = (os.getenv("REPLICA_S3_REGION", "") or "").strip() or None
        self.s3_endpoint_url = (os.getenv("REPLICA_S3_ENDPOINT_URL", "") or "").strip() or None
        self.s3_access_key = (os.getenv("REPLICA_S3_ACCESS_KEY_ID", "") or "").strip() or None
        self.s3_secret_key = (os.getenv("REPLICA_S3_SECRET_ACCESS_KEY", "") or "").strip() or None
        self.s3_prefix = (os.getenv("REPLICA_S3_PREFIX", "webchat-media") or "webchat-media").strip().strip("/")
        self.s3_public_base_url = (os.getenv("REPLICA_S3_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
        self.s3_presign_seconds = max(60, int(os.getenv("REPLICA_S3_PRESIGN_SECONDS", "86400") or 86400))
        self.s3_force_path_style = (
            (os.getenv("REPLICA_S3_FORCE_PATH_STYLE", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
        )

    @property
    def mode(self) -> str:
        if self.backend == "s3" and self.s3_bucket:
            return "s3"
        return "local"

    def _conversation_relative_path(
        self,
        *,
        session_key: str,
        run_id: str,
        category: str,
        filename: str,
    ) -> str:
        session = _safe_component(session_key, "main")
        run = _safe_component(run_id, "run")
        bucket = _safe_component(category, "generated")
        safe_filename = _safe_component(filename, "file.bin")
        return f"{session}/{run}/{bucket}/{safe_filename}"

    def _build_local_url(self, relative_path: str) -> str:
        encoded = urllib.parse.urlencode({"path": relative_path})
        return f"{self.url_prefix.rstrip('/')}?{encoded}"

    def _build_s3_key(self, relative_path: str) -> str:
        parts = [self.s3_prefix, self.tenant_schema, self.workspace_slug, relative_path]
        return "/".join(part.strip("/") for part in parts if part and part.strip("/"))

    def _s3_client_or_none(self) -> Any | None:
        if self.backend != "s3":
            return None
        if not self.s3_bucket:
            if self.log:
                self.log.warning("REPLICA_MEDIA_BACKEND=s3 but REPLICA_S3_BUCKET is not set. Falling back to local media.")
            return None
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3
        except Exception:
            if self.log:
                self.log.warning("boto3 is not installed. S3 upload disabled; keeping local media files.")
            return None
        kwargs: dict[str, Any] = {}
        if self.s3_region:
            kwargs["region_name"] = self.s3_region
        if self.s3_endpoint_url:
            kwargs["endpoint_url"] = self.s3_endpoint_url
        if self.s3_access_key:
            kwargs["aws_access_key_id"] = self.s3_access_key
        if self.s3_secret_key:
            kwargs["aws_secret_access_key"] = self.s3_secret_key
        if self.s3_force_path_style:
            kwargs["config"] = boto3.session.Config(s3={"addressing_style": "path"})
        self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client

    def _upload_to_s3_sync(self, *, key: str, payload: bytes, mime_type: str | None) -> tuple[str, str]:
        client = self._s3_client_or_none()
        if client is None or not self.s3_bucket:
            return "", ""
        put_kwargs: dict[str, Any] = {
            "Bucket": self.s3_bucket,
            "Key": key,
            "Body": payload,
        }
        if mime_type:
            put_kwargs["ContentType"] = mime_type
        client.put_object(**put_kwargs)
        if self.s3_public_base_url:
            quoted_key = urllib.parse.quote(key, safe="/._-")
            return key, f"{self.s3_public_base_url}/{quoted_key}"
        presigned = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.s3_bucket, "Key": key},
            ExpiresIn=self.s3_presign_seconds,
        )
        return key, str(presigned)

    async def store_bytes(
        self,
        *,
        session_key: str,
        run_id: str,
        category: str,
        filename: str,
        payload: bytes,
        mime_type: str | None = None,
    ) -> MediaLocation:
        relative_path = self._conversation_relative_path(
            session_key=session_key,
            run_id=run_id,
            category=category,
            filename=filename,
        )
        local_path = (self.local_root / relative_path).resolve()
        await asyncio.to_thread(local_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(local_path.write_bytes, payload)
        local_url = self._build_local_url(relative_path)

        guessed = (mime_type or "").strip().lower()
        if not guessed:
            guessed = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"

        s3_key = ""
        s3_url = ""
        if self.mode == "s3":
            key = self._build_s3_key(relative_path)
            try:
                s3_key, s3_url = await asyncio.to_thread(
                    self._upload_to_s3_sync,
                    key=key,
                    payload=payload,
                    mime_type=guessed,
                )
            except Exception as exc:
                if self.log:
                    self.log.warning("media upload to s3 failed for %s: %s", key, exc)
                s3_key, s3_url = "", ""

        download_url = s3_url or local_url
        return MediaLocation(
            local_path=local_path,
            relative_path=relative_path,
            local_url=local_url,
            download_url=download_url,
            s3_key=s3_key,
            s3_url=s3_url,
            mime_type=guessed,
            size_bytes=len(payload),
        )

    async def mirror_file(
        self,
        *,
        source_path: Path,
        session_key: str,
        run_id: str,
        category: str,
        preferred_name: str | None = None,
        mime_type: str | None = None,
    ) -> MediaLocation:
        source = source_path.expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(str(source))
        name = preferred_name or source.name or "file.bin"
        relative_path = self._conversation_relative_path(
            session_key=session_key,
            run_id=run_id,
            category=category,
            filename=name,
        )
        local_path = (self.local_root / relative_path).resolve()
        await asyncio.to_thread(local_path.parent.mkdir, parents=True, exist_ok=True)
        if source != local_path:
            await asyncio.to_thread(shutil.copyfile, source, local_path)
        payload = await asyncio.to_thread(local_path.read_bytes)
        return await self.store_bytes(
            session_key=session_key,
            run_id=run_id,
            category=category,
            filename=local_path.name,
            payload=payload,
            mime_type=mime_type,
        )
