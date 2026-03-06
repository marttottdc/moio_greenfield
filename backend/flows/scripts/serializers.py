from __future__ import annotations

import json
from typing import Iterable, List, Optional

from django.db import transaction
from django.db.models import Prefetch
from django.utils.text import slugify
from rest_framework import serializers

from ..models import Flow, FlowScript, FlowScriptVersion
from .validators import validate_script_payload


class FlowScriptVersionSerializer:
    """Utility helpers to serialize script version metadata."""

    @staticmethod
    def serialize(
        version: Optional[FlowScriptVersion], *, include_body: bool = False
    ) -> Optional[dict]:
        if version is None:
            return None
        parameters = version.parameters or {}
        return {
            "id": str(version.id),
            "version": version.version_number,
            "is_published": version.is_published,
            "published_at": version.published_at.isoformat()
            if version.published_at
            else None,
            "created_at": version.created_at.isoformat(),
            "notes": version.notes,
            **(
                {
                    "code": version.code,
                    "parameters": parameters,
                    "parameters_text": json.dumps(
                        parameters, indent=2, ensure_ascii=False
                    ),
                }
                if include_body
                else {}
            ),
        }


class FlowScriptSerializer:
    """High level serializer for scripts exposed to the builder UI."""

    @classmethod
    def serialize(
        cls, script: FlowScript, include_versions: bool = False
    ) -> dict:
        version_list = list(script.versions.all())
        latest_version = version_list[0] if version_list else None
        published_version = next(
            (version for version in version_list if version.is_published), None
        )
        data = {
            "id": str(script.id),
            "name": script.name,
            "slug": script.slug,
            "description": script.description,
            "flow_id": str(script.flow_id) if script.flow_id else None,
            "tenant_id": script.tenant_id,
            "latest_version": FlowScriptVersionSerializer.serialize(
                latest_version, include_body=True
            ),
            "published_version": FlowScriptVersionSerializer.serialize(
                published_version
            ),
        }
        if include_versions:
            versions = [
                FlowScriptVersionSerializer.serialize(version)
                for version in version_list
            ]
            data["versions"] = versions
        return data

    @classmethod
    def serialize_many(
        cls, scripts: Iterable[FlowScript], include_versions: bool = False
    ) -> List[dict]:
        return [cls.serialize(script, include_versions=include_versions) for script in scripts]

    @classmethod
    def for_flow(cls, flow: Flow) -> List[dict]:
        scripts = (
            flow.scripts.all()
            .select_related("flow", "tenant")
            .prefetch_related(
                Prefetch(
                    "versions",
                    queryset=FlowScriptVersion.objects.order_by(
                        "-version_number", "-created_at"
                    ),
                )
            )
            .order_by("name")
        )
        return cls.serialize_many(scripts, include_versions=True)

    @classmethod
    def for_tenant(cls, tenant) -> List[dict]:
        """
        Return all scripts available to a tenant (flow-scoped and global).

        The flow builder needs a tenant-wide catalog so a Flow Script node can
        reference scripts that are not tied to a specific Flow record.
        """
        scripts = (
            FlowScript.objects.filter(tenant=tenant)
            .select_related("flow", "tenant")
            .prefetch_related(
                Prefetch(
                    "versions",
                    queryset=FlowScriptVersion.objects.order_by(
                        "-version_number", "-created_at"
                    ),
                )
            )
            .order_by("name")
        )
        return cls.serialize_many(scripts, include_versions=True)


class FlowScriptCreateSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    code = serializers.CharField()
    params = serializers.JSONField(required=False, default=dict)
    flow_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_flow_id(self, value):
        if value is None:
            return None

        tenant = self.context.get("tenant")
        flow = Flow.objects.filter(id=value).first()
        if not flow or (tenant and flow.tenant_id != getattr(tenant, "id", None)):
            raise serializers.ValidationError("Flow not found for this tenant.")
        return flow

    def validate(self, attrs):
        tenant = self.context.get("tenant")
        if tenant is None:
            raise serializers.ValidationError({"tenant": "Tenant is required."})

        name = (attrs.get("name") or "").strip()
        description = (attrs.get("description") or "").strip()
        code = attrs.get("code") or ""
        params_value = attrs.get("params", {})

        if isinstance(params_value, dict):
            params_text = json.dumps(params_value, ensure_ascii=False)
        else:
            params_text = params_value if isinstance(params_value, str) else ""

        errors, _messages, params = validate_script_payload(
            name, description, code, params_text
        )
        if errors:
            raise serializers.ValidationError(errors)

        flow = attrs.pop("flow_id", None)
        if flow:
            attrs["flow"] = flow

        attrs["name"] = name
        attrs["description"] = description
        attrs["params"] = params
        attrs["code"] = code
        return attrs

    def create(self, validated_data):
        tenant = validated_data.pop("tenant")
        flow = validated_data.pop("flow", None)
        notes = (validated_data.pop("notes", "") or "").strip()

        with transaction.atomic():
            slug_value = self._unique_script_slug(validated_data["name"], tenant)
            script = FlowScript.objects.create(
                tenant=tenant,
                flow=flow,
                name=validated_data["name"],
                slug=slug_value,
                description=validated_data.get("description", ""),
            )
            FlowScriptVersion.objects.create(
                script=script,
                tenant=tenant,
                flow=flow,
                version_number=1,
                code=validated_data.get("code", ""),
                parameters=validated_data.get("params") or {},
                notes=notes,
            )
        return script

    def to_representation(self, instance):
        return FlowScriptSerializer.serialize(instance, include_versions=True)

    @staticmethod
    def _unique_script_slug(name: str, tenant) -> str:
        base_slug = slugify(name) or "script"
        slug_candidate = base_slug
        queryset = FlowScript.objects.all()
        if tenant:
            queryset = queryset.filter(tenant=tenant)
        suffix = 2
        while queryset.filter(slug=slug_candidate).exists():
            slug_candidate = f"{base_slug}-{suffix}"
            suffix += 1
        return slug_candidate
