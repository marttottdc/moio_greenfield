from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from .config import ModelConfig


@dataclass(slots=True)
class LlmResponse:
    text: str
    tool_calls: list[dict[str, Any]]
    raw_message: dict[str, Any]
    usage: dict[str, int]
    stop_reason: str = ""


class OpenAIModelClient:
    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self.client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.timeout_seconds)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        extra_user_content: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        response = await self._responses_create(
            input=self._messages_to_responses_input(messages, extra_user_content=extra_user_content),
            tools=self._to_responses_tools(tools),
        )
        return self._parse_response(response)

    async def complete_stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        extra_user_content: list[dict[str, Any]] | None = None,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LlmResponse:
        # Use responses API and forward the full text in one delta payload.
        # This keeps the frontend stream contract stable while migrating away from chat completions.
        result = await self.complete(messages=messages, tools=tools, extra_user_content=extra_user_content)
        if on_text_delta and result.text:
            await on_text_delta(result.text)
        return result

    async def _responses_create(self, *, input: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        normalized_input = self._sanitize_responses_input(input)
        normalized_input = await self._materialize_file_inputs(normalized_input)
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "input": normalized_input,
            "tools": tools if tools else None,
            "temperature": self.cfg.temperature,
            "max_output_tokens": self.cfg.max_output_tokens,
        }
        try:
            return await self.client.responses.create(**payload)
        except Exception as exc:
            # Some OpenAI-compatible vendors reject optional knobs.
            error_text = str(exc).lower()
            retry = dict(payload)
            changed = False
            if "supported values are: 'output_text' and 'refusal'" in error_text:
                retry["input"] = self._sanitize_responses_input(retry.get("input", []), force_assistant_output_text=True)
                changed = True
            if "invalid" in error_text and ".file_data" in error_text:
                retry["input"] = await self._materialize_file_inputs(retry.get("input", []), force_reupload=True)
                changed = True
            if "temperature" in error_text and "temperature" in retry:
                retry.pop("temperature", None)
                changed = True
            if ("max_output_tokens" in error_text or "max tokens" in error_text) and "max_output_tokens" in retry:
                retry.pop("max_output_tokens", None)
                changed = True
            if not changed:
                raise
            return await self.client.responses.create(**retry)

    async def _materialize_file_inputs(
        self,
        items: list[dict[str, Any]],
        *,
        force_reupload: bool = False,
    ) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        use_openai_file_upload = self._is_openai_upload_available()
        output: list[dict[str, Any]] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content")
            if not isinstance(content, list):
                output.append(entry)
                continue
            next_content: list[dict[str, Any]] = []
            changed = False
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = str(part.get("type", "")).strip().lower()
                if part_type != "input_file":
                    next_content.append(part)
                    continue

                has_file_id = bool(str(part.get("file_id", "")).strip())
                if has_file_id and not force_reupload:
                    next_content.append({"type": "input_file", "file_id": str(part.get("file_id", "")).strip()})
                    continue

                filename = str(part.get("filename", "")).strip() or "attachment.bin"
                file_data = str(part.get("file_data", "")).strip()
                if not file_data:
                    next_content.append({"type": "input_text", "text": f"[attachment omitted: {filename}]"})
                    changed = True
                    continue

                if not use_openai_file_upload:
                    # Non-OpenAI providers can reject input_file payloads; keep a compact textual pointer.
                    next_content.append(
                        {
                            "type": "input_text",
                            "text": f"[attachment available in local workspace but direct file upload unsupported for provider: {filename}]",
                        }
                    )
                    changed = True
                    continue

                file_bytes = self._decode_attachment_payload(file_data)
                if not file_bytes:
                    next_content.append({"type": "input_text", "text": f"[attachment decode failed: {filename}]"})
                    changed = True
                    continue

                try:
                    uploaded = await self.client.files.create(file=(filename, file_bytes), purpose="user_data")
                    file_id = str(getattr(uploaded, "id", "") or "").strip()
                except Exception:
                    file_id = ""
                if file_id:
                    next_content.append({"type": "input_file", "file_id": file_id})
                else:
                    next_content.append({"type": "input_text", "text": f"[attachment upload failed: {filename}]"})
                changed = True

            if changed:
                updated = dict(entry)
                updated["content"] = next_content
                output.append(updated)
            else:
                output.append(entry)
        return output

    def _is_openai_upload_available(self) -> bool:
        provider = str(getattr(self.cfg, "provider", "")).strip().lower()
        base_url = str(getattr(self.cfg, "base_url", "") or "").strip().lower()
        if provider == "openai":
            return True
        return "openai.com" in base_url

    @staticmethod
    def _decode_attachment_payload(file_data: str) -> bytes:
        value = str(file_data or "").strip()
        if not value:
            return b""
        if value.startswith("data:"):
            comma = value.find(",")
            if comma >= 0:
                value = value[comma + 1 :]
        try:
            return base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            return b""

    @classmethod
    def _sanitize_responses_input(
        cls,
        items: list[dict[str, Any]],
        *,
        force_assistant_output_text: bool = False,
    ) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        normalized: list[dict[str, Any]] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role", "")).strip().lower()
            if role != "assistant":
                normalized.append(entry)
                continue

            content = entry.get("content")
            if not isinstance(content, list):
                normalized.append(entry)
                continue

            next_content: list[dict[str, Any]] = []
            changed = False
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = str(part.get("type", "")).strip()
                next_part = dict(part)
                if part_type == "input_text" or (force_assistant_output_text and part_type not in {"output_text", "refusal"}):
                    next_part["type"] = "output_text"
                    changed = True
                next_content.append(next_part)
            if changed:
                updated = dict(entry)
                updated["content"] = next_content
                normalized.append(updated)
            else:
                normalized.append(entry)
        return normalized

    def _parse_response(self, response: Any) -> LlmResponse:
        text = str(getattr(response, "output_text", "") or "").strip()
        output = getattr(response, "output", None)
        if not text:
            text = self._extract_text_from_output(output)
        tool_calls = self._extract_tool_calls_from_output(output)
        raw_message: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            raw_message["tool_calls"] = tool_calls
        usage = self._coerce_usage(getattr(response, "usage", None))
        stop_reason = self._coerce_stop_reason(response, output)
        return LlmResponse(text=text, tool_calls=tool_calls, raw_message=raw_message, usage=usage, stop_reason=stop_reason)

    @classmethod
    def _extract_text_content(cls, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for entry in content:
                if isinstance(entry, dict):
                    text = entry.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
                        continue
                    text = entry.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            return "\n".join(parts).strip()
        return ""

    @classmethod
    def _normalize_extra_user_content(cls, extra_user_content: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not isinstance(extra_user_content, list):
            return []
        normalized: list[dict[str, Any]] = []
        for entry in extra_user_content:
            if not isinstance(entry, dict):
                continue
            entry_type = str(entry.get("type", "")).strip().lower()
            if entry_type == "input_text":
                text = str(entry.get("text", "")).strip()
                if text:
                    normalized.append({"type": "input_text", "text": text})
                continue
            if entry_type == "input_image":
                image_url = str(entry.get("image_url", "")).strip()
                if image_url:
                    normalized.append({"type": "input_image", "image_url": image_url})
                continue
            if entry_type == "input_file":
                file_data = str(entry.get("file_data", "")).strip()
                if not file_data:
                    continue
                payload: dict[str, Any] = {"type": "input_file", "file_data": file_data}
                filename = str(entry.get("filename", "")).strip()
                if filename:
                    payload["filename"] = filename
                normalized.append(payload)
        return normalized

    @classmethod
    def _messages_to_responses_input(
        cls,
        messages: list[dict[str, Any]],
        *,
        extra_user_content: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        last_user_index = -1

        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "")).strip().lower()
            if role not in {"system", "user", "assistant", "tool"}:
                continue

            if role == "tool":
                call_id = str(message.get("tool_call_id", "")).strip()
                output_text = cls._extract_text_content(message.get("content"))
                if call_id:
                    items.append({"type": "function_call_output", "call_id": call_id, "output": output_text})
                elif output_text:
                    items.append(
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": f"Tool output:\n{output_text}"}],
                        }
                    )
                    last_user_index = len(items) - 1
                continue

            text = cls._extract_text_content(message.get("content"))
            content: list[dict[str, Any]] = []
            if text:
                content_type = "output_text" if role == "assistant" else "input_text"
                content.append({"type": content_type, "text": text})
            items.append({"role": role, "content": content})
            if role == "user":
                last_user_index = len(items) - 1

            if role == "assistant":
                raw_calls = message.get("tool_calls")
                if isinstance(raw_calls, list):
                    for call in raw_calls:
                        if not isinstance(call, dict):
                            continue
                        function = call.get("function") if isinstance(call.get("function"), dict) else {}
                        name = str(function.get("name", "")).strip()
                        if not name:
                            continue
                        arguments = str(function.get("arguments", "{}")).strip() or "{}"
                        call_id = str(call.get("id") or "").strip() or f"call_{len(items) + 1}"
                        items.append(
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": name,
                                "arguments": arguments,
                            }
                        )

        extra_items = cls._normalize_extra_user_content(extra_user_content)
        if extra_items:
            if 0 <= last_user_index < len(items):
                content = items[last_user_index].get("content")
                if isinstance(content, list):
                    content.extend(extra_items)
                else:
                    items[last_user_index]["content"] = list(extra_items)
            else:
                items.append({"role": "user", "content": list(extra_items)})

        return items

    @staticmethod
    def _to_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            if str(tool.get("type", "")).strip() != "function":
                normalized.append(tool)
                continue
            function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
            name = str(function.get("name", "")).strip()
            if not name:
                continue
            normalized.append(
                {
                    "type": "function",
                    "name": name,
                    "description": str(function.get("description", "")).strip(),
                    "parameters": function.get("parameters", {"type": "object", "properties": {}}),
                }
            )
        return normalized

    @classmethod
    def _extract_text_from_output(cls, output: Any) -> str:
        if not isinstance(output, (list, tuple)):
            return ""
        parts: list[str] = []
        for item in output:
            item_type = str(getattr(item, "type", "") or (item.get("type") if isinstance(item, dict) else "")).strip()
            if item_type == "message":
                content = getattr(item, "content", None)
                if content is None and isinstance(item, dict):
                    content = item.get("content")
                if not isinstance(content, (list, tuple)):
                    continue
                for chunk in content:
                    chunk_type = str(
                        getattr(chunk, "type", "") or (chunk.get("type") if isinstance(chunk, dict) else "")
                    ).strip()
                    if chunk_type not in {"output_text", "text", "input_text"}:
                        continue
                    text = getattr(chunk, "text", None)
                    if text is None and isinstance(chunk, dict):
                        text = chunk.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            elif item_type in {"output_text", "text"}:
                text = getattr(item, "text", None)
                if text is None and isinstance(item, dict):
                    text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return "\n".join(parts).strip()

    @staticmethod
    def _extract_tool_calls_from_output(output: Any) -> list[dict[str, Any]]:
        if not isinstance(output, (list, tuple)):
            return []
        tool_calls: list[dict[str, Any]] = []
        for item in output:
            item_type = str(getattr(item, "type", "") or (item.get("type") if isinstance(item, dict) else "")).strip()
            if item_type != "function_call":
                continue
            call_id = str(getattr(item, "call_id", "") or (item.get("call_id") if isinstance(item, dict) else "")).strip()
            if not call_id:
                call_id = str(getattr(item, "id", "") or (item.get("id") if isinstance(item, dict) else "")).strip()
            name = str(getattr(item, "name", "") or (item.get("name") if isinstance(item, dict) else "")).strip()
            arguments = (
                str(getattr(item, "arguments", "") or (item.get("arguments") if isinstance(item, dict) else "")).strip()
                or "{}"
            )
            if not name:
                continue
            tool_calls.append(
                {
                    "id": call_id or "",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": arguments,
                    },
                }
            )
        return tool_calls

    @staticmethod
    def _coerce_usage(raw_usage: Any) -> dict[str, int]:
        if raw_usage is None:
            return {"input": 0, "output": 0, "total": 0}

        def _as_int(value: Any) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return 0
            return parsed if parsed > 0 else 0

        if isinstance(raw_usage, dict):
            prompt = _as_int(raw_usage.get("input_tokens")) or _as_int(raw_usage.get("prompt_tokens"))
            completion = _as_int(raw_usage.get("output_tokens")) or _as_int(raw_usage.get("completion_tokens"))
            total = _as_int(raw_usage.get("total_tokens"))
        else:
            prompt = _as_int(getattr(raw_usage, "input_tokens", 0)) or _as_int(getattr(raw_usage, "prompt_tokens", 0))
            completion = _as_int(getattr(raw_usage, "output_tokens", 0)) or _as_int(
                getattr(raw_usage, "completion_tokens", 0)
            )
            total = _as_int(getattr(raw_usage, "total_tokens", 0))

        if total == 0:
            total = prompt + completion
        return {"input": prompt, "output": completion, "total": total}

    @staticmethod
    def _coerce_stop_reason(response: Any, output: Any) -> str:
        direct = str(getattr(response, "stop_reason", "") or "").strip()
        if direct:
            return direct

        status = str(getattr(response, "status", "") or "").strip().lower()
        if status:
            if status == "completed":
                return "stop"
            if status in {"incomplete", "failed", "cancelled"}:
                details = getattr(response, "incomplete_details", None)
                reason = ""
                if isinstance(details, dict):
                    reason = str(details.get("reason", "") or "").strip().lower()
                else:
                    reason = str(getattr(details, "reason", "") or "").strip().lower()
                return reason or status

        if isinstance(output, (list, tuple)):
            for item in reversed(output):
                item_status = str(
                    getattr(item, "status", "") or (item.get("status") if isinstance(item, dict) else "")
                ).strip()
                if item_status:
                    return item_status

        return ""
